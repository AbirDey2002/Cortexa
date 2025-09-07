from datetime import datetime
import os
import subprocess
import asyncio
from PIL import Image, ImageDraw
import requests
import fitz
from api.v1.endpoints.generator import run_generator
from models.usecase.usecase import UsecaseMetadata
from services.llm.pf_image2text_automation.asset_invoker import AssetInvoker
from deps import get_db
from models.file_processing.file_workflow_tracker import FileWorkflowTracker
from models.file_processing.ocr_records import OCROutputs, OCRInfo
from concurrent.futures import ThreadPoolExecutor
from core.config import HostingConfigs


class OCRPipeline:
    def __init__(self, blob_url, file_id, api_key, username, password, asset_id, num_workers=4, batch_size=10, max_retries=3):
        self.blob_url = blob_url
        self.file_id = file_id
        self.num_workers = num_workers
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.asset_invoker = AssetInvoker(api_key, username, password, asset_id)

    def download_blob(self, blob_url):
        local_filename = os.path.basename(blob_url.split('?')[0])
        response = requests.get(blob_url, stream=True)
        if response.status_code != 200:
            raise Exception(f"Failed to download file from {blob_url}: Status code {response.status_code}")
        with open(local_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return local_filename

    def docx_to_pdf(self, docx_file_path):
        if not os.path.isfile(docx_file_path):
            raise FileNotFoundError(f"File not found: {docx_file_path}")
        directory, filename = os.path.split(docx_file_path)
        base_name, _ = os.path.splitext(filename)
        convert_command = [
            "soffice",
            "--headless",
            "--convert-to", "pdf",
            docx_file_path,
            "--outdir", directory
        ]
        subprocess.run(convert_command, check=True)
        generated_pdf_path = os.path.join(directory, f"{base_name}.pdf")
        if not os.path.exists(generated_pdf_path):
            raise FileNotFoundError(f"Converted PDF not found: {generated_pdf_path}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_pdf_filename = f"{base_name}_{timestamp}.pdf"
        new_pdf_path = os.path.join(directory, new_pdf_filename)
        os.rename(generated_pdf_path, new_pdf_path)
        return new_pdf_path

    def convert_pdf_to_images(self, pdf_file):
        base_name = os.path.splitext(os.path.basename(pdf_file))[0]
        folder_path = base_name + "_" + datetime.now().strftime('%Y%m%d_%H%M%S')
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        doc = fitz.open(pdf_file)
        for page_number in range(doc.page_count):
            page = doc.load_page(page_number)
            pix = page.get_pixmap(dpi=300)
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"Page {page_number + 1}", fill="red")
            image_filename = f"{page_number + 1:03d}.png"
            image_filepath = os.path.join(folder_path, image_filename)
            img.save(image_filepath)
        doc.close()
        return folder_path

    async def _process_batch(self, batch, semaphore, status_list, outputs):
        for attempt in range(self.max_retries):
            for fp in batch:
                status_list[os.path.basename(fp)] = "in-progress"
            async with semaphore:
                try:
                    result = await self.asset_invoker.invoke_asset(batch)
                    db = next(get_db())
                    try:
                        for j, fp in enumerate(batch):
                            image_name = os.path.basename(fp)
                            image_output = result[j] if j < len(result) else ""
                            status_list[image_name] = "success"
                            outputs[image_name] = image_output
                            try:
                                page_num = int(os.path.splitext(image_name)[0])
                            except Exception:
                                page_num = 0
                            record = db.query(OCROutputs).filter(
                                OCROutputs.file_id == self.file_id,
                                OCROutputs.page_number == page_num
                            ).first()
                            if not record:
                                record = OCROutputs(
                                    file_id=self.file_id,
                                    page_number=page_num,
                                    page_text=image_output,
                                    is_completed=True
                                )
                                db.add(record)
                            else:
                                record.page_text = image_output
                                record.error_msg = None
                                record.is_completed = True
                        db.commit()
                    finally:
                        db.close()
                    return
                except asyncio.TimeoutError:
                    db = next(get_db())
                    try:
                        for fp in batch:
                            image_name = os.path.basename(fp)
                            status_list[image_name] = "error"
                            try:
                                page_num = int(os.path.splitext(image_name)[0])
                            except Exception:
                                page_num = 0
                            record = db.query(OCROutputs).filter(
                                OCROutputs.file_id == self.file_id,
                                OCROutputs.page_number == page_num
                            ).first()
                            if not record:
                                record = OCROutputs(
                                    file_id=self.file_id,
                                    page_number=page_num,
                                    page_text="",
                                    error_msg="Timeout occurred during asset invocation",
                                    is_completed=False
                                )
                                db.add(record)
                            else:
                                record.page_text = ""
                                record.error_msg = "Timeout occurred during asset invocation"
                                record.is_completed = False
                        db.commit()
                    except Exception:
                        db.rollback()
                    finally:
                        db.close()
                    return
                except Exception:
                    pass
            await asyncio.sleep(1)

        db = next(get_db())
        try:
            for fp in batch:
                image_name = os.path.basename(fp)
                status_list[image_name] = "error"
                try:
                    page_num = int(os.path.splitext(image_name)[0])
                except Exception:
                    page_num = 0
                record = db.query(OCROutputs).filter(
                    OCROutputs.file_id == self.file_id,
                    OCROutputs.page_number == page_num
                ).first()
                if not record:
                    record = OCROutputs(
                        file_id=self.file_id,
                        page_number=page_num,
                        page_text="",
                        error_msg="Processing failed after maximum retries",
                        is_completed=False
                    )
                    db.add(record)
                else:
                    record.page_text = ""
                    record.error_msg = "Processing failed after maximum retries"
                    record.is_completed = False
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    async def _display_statuses(self, status_list):
        while True:
            await asyncio.sleep(1)

    async def generate_final_info(self, folder_path):
        image_files = sorted(os.listdir(folder_path))
        image_file_paths = [os.path.join(folder_path, f) for f in image_files if os.path.isfile(os.path.join(folder_path, f))]
        image_names = [os.path.basename(fp) for fp in image_file_paths]
        status_list = {name: "pending" for name in image_names}
        outputs = {name: "" for name in image_names}
        batches_dict = {}
        for i in range(0, len(image_file_paths), self.batch_size):
            batch_key = i // self.batch_size
            batches_dict[batch_key] = image_file_paths[i:i + self.batch_size]
        semaphore = asyncio.Semaphore(self.num_workers)
        display_task = asyncio.create_task(self._display_statuses(status_list))
        tasks = [asyncio.create_task(self._process_batch(batch, semaphore, status_list, outputs))
                 for batch in batches_dict.values()]
        for task in tasks:
            await task
        display_task.cancel()
        try:
            await display_task
        except asyncio.CancelledError:
            pass
        return image_names, outputs, status_list

    async def _run_pipeline_async(self):
        local_file = self.download_blob(self.blob_url)
        pdf_path = None
        try:
            if local_file.lower().endswith('.docx'):
                pdf_path = self.docx_to_pdf(local_file)
                os.remove(local_file)
            elif local_file.lower().endswith('.pdf'):
                pdf_path = local_file
            else:
                raise ValueError("Unsupported file type. Only DOCX and PDF are supported.")
            image_folder = self.convert_pdf_to_images(pdf_path)
            image_names, outputs, status_list = await self.generate_final_info(image_folder)
            total_pages = len(image_names)
            completed_pages = sum(1 for s in status_list.values() if s == "success")
            error_pages = sum(1 for s in status_list.values() if s == "error")
            db = next(get_db())
            try:
                ocr_info = db.query(OCRInfo).filter(OCRInfo.file_id == self.file_id).first()
                if not ocr_info:
                    ocr_info = OCRInfo(
                        file_id=self.file_id,
                        total_pages=total_pages,
                        completed_pages=completed_pages,
                        error_pages=error_pages
                    )
                    db.add(ocr_info)
                else:
                    ocr_info.total_pages = total_pages
                    ocr_info.completed_pages = completed_pages
                    ocr_info.error_pages = error_pages
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            if pdf_path:
                os.remove(pdf_path)
            if image_folder and os.path.exists(image_folder):
                for file in os.listdir(image_folder):
                    os.remove(os.path.join(image_folder, file))
                os.rmdir(image_folder)
            return image_names
        except Exception as e:
            if local_file and os.path.exists(local_file):
                os.remove(local_file)
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
            if 'image_folder' in locals() and image_folder and os.path.exists(image_folder):
                for file in os.listdir(image_folder):
                    os.remove(os.path.join(image_folder, file))
                os.rmdir(image_folder)
            raise e

    def run(self):
        try:
            db = next(get_db())
            try:
                tracker = FileWorkflowTracker(
                    file_id=self.file_id,
                    text_extraction="Not Started",
                )
                db.add(tracker)
                db.commit()
            except Exception as e:
                db.rollback()
                raise e
            finally:
                db.close()

            db = next(get_db())
            try:
                tracker = db.query(FileWorkflowTracker).filter(FileWorkflowTracker.file_id == self.file_id).first()
                if tracker:
                    tracker.text_extraction = "In Progress"
                db.commit()
            except Exception as e:
                db.rollback()
                raise e
            finally:
                db.close()

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            image_names = loop.run_until_complete(self._run_pipeline_async())

            db = next(get_db())
            try:
                tracker = db.query(FileWorkflowTracker).filter(FileWorkflowTracker.file_id == self.file_id).first()
                if tracker:
                    tracker.text_extraction = "Completed"
                db.commit()
            except Exception as e:
                db.rollback()
                raise e
            finally:
                db.close()
            return image_names
        except Exception as e:
            db = next(get_db())
            try:
                tracker = db.query(FileWorkflowTracker).filter(FileWorkflowTracker.file_id == self.file_id).first()
                if tracker:
                    tracker.error_msg = str(e)
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            raise e


def run_parallel_ocr(batch, api_key, username, password, asset_id, num_workers, batch_size, max_retries):
    def process_single_file(file_data):
        blob_url, file_id = file_data
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            pipeline_instance = OCRPipeline(
                blob_url=blob_url,
                file_id=file_id,
                api_key=api_key,
                username=username,
                password=password,
                asset_id=asset_id,
                num_workers=num_workers,
                batch_size=batch_size,
                max_retries=max_retries
            )
            try:
                result = loop.run_until_complete(pipeline_instance._run_pipeline_async())
                return result
            finally:
                loop.close()
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        results = list(executor.map(process_single_file, batch))
    return results


def run_all_ocr_batches(usecase_id, ocr_data, batch_size, api_key, username, password, asset_id, num_workers, ocr_batch_size, max_retries):
    try:
        db = next(get_db())
        try:
            usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            if usecase:
                usecase.text_extraction = "In Progress"
                db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

        total_files = len(ocr_data)
        for i in range(0, total_files, batch_size):
            current_batch = ocr_data[i:i + batch_size]
            run_parallel_ocr(current_batch, api_key, username, password, asset_id, num_workers, ocr_batch_size, max_retries)

        db = next(get_db())
        try:
            usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            if usecase:
                usecase.text_extraction = "Completed"
                db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
        return {"status": "ok"}
    except Exception as e:
        raise e


