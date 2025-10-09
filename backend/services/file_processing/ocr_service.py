from datetime import datetime
import os
import subprocess
import asyncio
from PIL import Image, ImageDraw
import requests
import fitz
from models.usecase.usecase import UsecaseMetadata
# PF OCR invoker removed
from deps import get_db
from models.file_processing.file_workflow_tracker import FileWorkflowTracker
from models.file_processing.ocr_records import OCROutputs, OCRInfo
from concurrent.futures import ThreadPoolExecutor
from core.config import HostingConfigs, OCRServiceConfigs
import logging

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Prevent duplicate handlers
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
# Prevent propagation to avoid duplicate messages
logger.propagate = False


class OCRPipeline:
    def __init__(self, blob_url, file_id, api_key, username, password, asset_id, num_workers=4, batch_size=10, max_retries=3):
        self.blob_url = blob_url
        self.file_id = file_id
        self.num_workers = num_workers
        self.batch_size = batch_size
        self.max_retries = max_retries
        raise RuntimeError("PF OCR invoker removed from codebase")

    def download_blob(self, blob_url):
        """Download file from blob URL with detailed logging"""
        logger.info(f"Starting download from blob URL: {blob_url}")
        local_filename = os.path.basename(blob_url.split('?')[0])
        logger.info(f"Local filename will be: {local_filename}")
        
        try:
            response = requests.get(blob_url, stream=True)
            if response.status_code != 200:
                logger.error(f"Failed to download file from {blob_url}: Status code {response.status_code}")
                raise Exception(f"Failed to download file from {blob_url}: Status code {response.status_code}")
            
            logger.info(f"Successfully connected to blob URL, downloading file...")
            with open(local_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(local_filename)
            logger.info(f"Successfully downloaded file: {local_filename} ({file_size} bytes)")
            return local_filename
        except Exception as e:
            logger.error(f"Error downloading file from {blob_url}: {e}", exc_info=True)
            raise

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
        """Convert PDF to images and save in temp directory"""
        logger.info(f"Starting PDF to images conversion for: {pdf_file}")
        base_name = os.path.splitext(os.path.basename(pdf_file))[0]
        
        # Create folder in temp directory
        temp_dir = os.path.join(os.getcwd(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        folder_path = os.path.join(temp_dir, base_name + "_" + datetime.now().strftime('%Y%m%d_%H%M%S'))
        
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            logger.info(f"Created output directory: {folder_path}")
        
        try:
            doc = fitz.open(pdf_file)
            page_count = doc.page_count
            logger.info(f"Number of PDF pages: {page_count}")
            
            for page_number in range(page_count):
                logger.info(f"Processing page {page_number + 1}/{page_count}")
                page = doc.load_page(page_number)
                pix = page.get_pixmap(dpi=300)
                mode = "RGBA" if pix.alpha else "RGB"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                draw = ImageDraw.Draw(img)
                draw.text((10, 10), f"Page {page_number + 1}", fill="red")
                image_filename = f"{page_number + 1:03d}.png"
                image_filepath = os.path.join(folder_path, image_filename)
                img.save(image_filepath)
                logger.info(f"Saved page {page_number + 1} as: {image_filename}")
            
            doc.close()
            logger.info(f"Successfully converted PDF to {page_count} images in: {folder_path}")
            return folder_path
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}", exc_info=True)
            raise

    async def _process_batch(self, batch, semaphore, status_list, outputs):
        """Process a batch of image file paths using the asset invoker with retries and detailed logging"""
        batch_files = [os.path.basename(fp) for fp in batch]
        logger.info(f"Starting batch processing for files: {batch_files}")
        
        for attempt in range(self.max_retries):
            logger.info(f"Batch processing attempt {attempt + 1}/{self.max_retries} for files: {batch_files}")
            for fp in batch:
                status_list[os.path.basename(fp)] = "in-progress"
            async with semaphore:
                try:
                    raise RuntimeError("PF OCR path removed; no OCR invoker available")
                    db = next(get_db())
                    try:
                        for j, fp in enumerate(batch):
                            image_name = os.path.basename(fp)
                            image_output = result[j] if j < len(result) else ""
                            status_list[image_name] = "success"
                            outputs[image_name] = image_output
                            logger.info(f"Adding to database: page_number: {image_name}, text_length: {len(image_output)}")
                            
                            # Log the extracted text from OCR agent (with security controls)
                            if image_output and len(image_output.strip()) > 0:
                                if OCRServiceConfigs.LOG_OCR_TEXT:
                                    logger.info(f"OCR Agent Output for {image_name}:")
                                    logger.info(f"--- START OCR TEXT ---")
                                    
                                    # Limit text length to prevent sensitive content exposure
                                    text_to_log = image_output.strip()
                                    if len(text_to_log) > OCRServiceConfigs.OCR_TEXT_LOG_MAX_LENGTH:
                                        text_to_log = text_to_log[:OCRServiceConfigs.OCR_TEXT_LOG_MAX_LENGTH] + "... [TRUNCATED FOR SECURITY]"
                                    
                                    logger.info(text_to_log)
                                    logger.info(f"--- END OCR TEXT ---")
                                else:
                                    logger.info(f"OCR Agent extracted text for {image_name} (content logging disabled for security)")
                            else:
                                logger.warning(f"OCR Agent returned empty/no text for {image_name}")
                            
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
                                logger.info(f"Created new OCR output record for page {page_num}")
                            else:
                                record.page_text = image_output
                                record.error_msg = None
                                record.is_completed = True
                                logger.info(f"Updated existing OCR output record for page {page_num}")
                        db.commit()
                        logger.info(f"Successfully processed and saved OCR results for batch: {batch_files}")
                    except Exception as db_error:
                        db.rollback()
                        logger.error(f"Database error: {db_error}", exc_info=True)
                        raise
                    finally:
                        db.close()
                    return
                except asyncio.TimeoutError:
                    logger.warning(f"Batch {batch_files} timed out after asset invocation. Marking as error.")
                    db = next(get_db())
                    try:
                        for fp in batch:
                            image_name = os.path.basename(fp)
                            status_list[image_name] = "error"
                            logger.info(f"Adding to database: page_number: {image_name} with timeout error")
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
                        logger.info(f"Saved timeout error records for batch: {batch_files}")
                    except Exception as db_error:
                        db.rollback()
                        logger.error(f"Database error: {db_error}", exc_info=True)
                    finally:
                        db.close()
                    return
                except Exception as e:
                    logger.error(f"Error processing batch {batch_files} on attempt {attempt + 1}/{self.max_retries}: {e}. Retrying...", exc_info=True)
                await asyncio.sleep(1)

        logger.error(f"All retry attempts failed for batch: {batch_files}. Marking as final errors.")
        db = next(get_db())
        try:
            for fp in batch:
                image_name = os.path.basename(fp)
                status_list[image_name] = "error"
                logger.info(f"Page: {image_name} - Status: {status_list[image_name]}")
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
            logger.info(f"Saved final error records for batch: {batch_files}")
        except Exception as db_error:
            db.rollback()
            logger.error(f"Database error: {db_error}", exc_info=True)
        finally:
            db.close()

    async def _display_statuses(self, status_list):
        while True:
            await asyncio.sleep(1)

    async def generate_final_info(self, folder_path):
        """Generate OCR results from image folder with detailed logging"""
        logger.info(f"Starting OCR processing for images in: {folder_path}")
        image_files = sorted(os.listdir(folder_path))
        image_file_paths = [os.path.join(folder_path, f) for f in image_files if os.path.isfile(os.path.join(folder_path, f))]
        image_names = [os.path.basename(fp) for fp in image_file_paths]
        
        logger.info(f"Found {len(image_file_paths)} images to process: {image_names}")
        
        status_list = {name: "pending" for name in image_names}
        outputs = {name: "" for name in image_names}
        batches_dict = {}
        
        # Create batches
        for i in range(0, len(image_file_paths), self.batch_size):
            batch_key = i // self.batch_size
            batches_dict[batch_key] = image_file_paths[i:i + self.batch_size]
        
        logger.info(f"Created {len(batches_dict)} batches with batch_size={self.batch_size}, num_workers={self.num_workers}")
        
        semaphore = asyncio.Semaphore(self.num_workers)
        display_task = asyncio.create_task(self._display_statuses(status_list))
        
        # Process all batches
        tasks = [asyncio.create_task(self._process_batch(batch, semaphore, status_list, outputs))
                 for batch in batches_dict.values()]
        
        logger.info("Starting parallel batch processing...")
        for task in tasks:
            await task
        
        display_task.cancel()
        try:
            await display_task
        except asyncio.CancelledError:
            pass
        
        # Log final status summary
        pending = sum(1 for s in status_list.values() if s == "pending")
        in_progress = sum(1 for s in status_list.values() if s == "in-progress")
        success = sum(1 for s in status_list.values() if s == "success")
        error = sum(1 for s in status_list.values() if s == "error")
        logger.info(f"OCR processing complete. Pending: {pending}, In-progress: {in_progress}, Success: {success}, Error: {error}")
        
        # Log extracted text summary
        total_chars = sum(len(text) for text in outputs.values() if text)
        pages_with_text = sum(1 for text in outputs.values() if text and text.strip())
        logger.info(f"OCR Results Summary: {pages_with_text}/{len(outputs)} pages extracted text, total {total_chars} characters")
        
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
        """Run the complete OCR pipeline with comprehensive logging"""
        logger.info(f"Starting OCR pipeline for file_id: {self.file_id}")
        logger.info(f"Blob URL: {self.blob_url}")
        logger.info(f"Configuration - workers: {self.num_workers}, batch_size: {self.batch_size}, max_retries: {self.max_retries}")
        
        try:
            # Create initial workflow tracker
            logger.info("Creating workflow tracker record")
            db = next(get_db())
            try:
                tracker = FileWorkflowTracker(
                    file_id=self.file_id,
                    text_extraction="Not Started",
                )
                db.add(tracker)
                db.commit()
                logger.info("Successfully created workflow tracker")
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating tracker: {e}", exc_info=True)
                raise e
            finally:
                db.close()

            # Update status to In Progress
            logger.info("Updating workflow status to 'In Progress'")
            db = next(get_db())
            try:
                tracker = db.query(FileWorkflowTracker).filter(FileWorkflowTracker.file_id == self.file_id).first()
                if tracker:
                    tracker.text_extraction = "In Progress"
                    logger.info("Successfully updated tracker to 'In Progress'")
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating tracker to In Progress: {e}", exc_info=True)
                raise e
            finally:
                db.close()

            # Run the main OCR pipeline
            logger.info("Starting async OCR pipeline execution")
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            image_names = loop.run_until_complete(self._run_pipeline_async())
            logger.info(f"OCR pipeline completed successfully. Processed images: {image_names}")

            # Update status to Completed
            logger.info("Updating workflow status to 'Completed'")
            db = next(get_db())
            try:
                tracker = db.query(FileWorkflowTracker).filter(FileWorkflowTracker.file_id == self.file_id).first()
                if tracker:
                    tracker.text_extraction = "Completed"
                    logger.info("Successfully updated tracker to 'Completed'")
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating tracker to Completed: {e}", exc_info=True)
                raise e
            finally:
                db.close()
            
            logger.info(f"OCR pipeline completed successfully for file_id: {self.file_id}")
            return image_names
            
        except Exception as e:
            logger.error(f"OCR pipeline failed for file_id: {self.file_id}. Error: {e}", exc_info=True)
            
            # Update tracker with error message
            db = next(get_db())
            try:
                tracker = db.query(FileWorkflowTracker).filter(FileWorkflowTracker.file_id == self.file_id).first()
                if tracker:
                    tracker.error_msg = str(e)
                    tracker.text_extraction = "Failed"
                    logger.info("Updated tracker with error message")
                db.commit()
            except Exception as db_error:
                db.rollback()
                logger.error(f"Error updating tracker with error message: {db_error}", exc_info=True)
            finally:
                db.close()
            raise e


def run_parallel_ocr(batch, api_key, username, password, asset_id, num_workers, batch_size, max_retries):
    """
    Runs OCR processing on a batch of files in parallel with detailed logging.
    
    Args:
        batch: List of tuples containing (blob_url, file_id)
        api_key: API key for the PF service
        username: Username for the PF service
        password: Password for the PF service
        asset_id: Asset ID for the PF service
        num_workers: Number of parallel workers
        batch_size: Size of each OCR batch
        max_retries: Maximum number of retries for OCR processing
        
    Returns:
        List of processing results for each file
    """
    logger.info(f"Starting parallel OCR processing for batch of {len(batch)} files")
    logger.info(f"Files in batch: {[file_id for _, file_id in batch]}")
    
    def process_single_file(file_data):
        blob_url, file_id = file_data
        logger.info(f"Starting OCR processing for file: {file_id}")
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
                logger.info(f"Successfully completed OCR processing for file: {file_id}")
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Error processing file {file_id}: {str(e)}", exc_info=True)
            return None
    
    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        results = list(executor.map(process_single_file, batch))
    
    successful_results = [r for r in results if r is not None]
    logger.info(f"OCR processing complete for current batch. {len(successful_results)}/{len(batch)} files processed successfully")
    return results


def run_all_ocr_batches(usecase_id, ocr_data, batch_size, api_key, username, password, asset_id, num_workers, ocr_batch_size, max_retries):
    """
    Process OCR data in batches sequentially until all files are processed.
    
    Args:
        usecase_id: The usecase ID to update status for
        ocr_data: List of tuples containing (blob_url, file_id)
        batch_size: Size of each batch to process
        api_key: API key for the PF service
        username: Username for the PF service
        password: Password for the PF service
        asset_id: Asset ID for the PF service
        num_workers: Number of parallel workers
        ocr_batch_size: Size of OCR batches
        max_retries: Maximum number of retries for OCR processing
        
    Returns:
        dict: Status response
    """
    logger.info(f"Starting OCR processing for usecase: {usecase_id}")
    logger.info(f"Total files to process: {len(ocr_data)}, batch_size: {batch_size}")
    logger.info(f"Configuration - workers: {num_workers}, ocr_batch_size: {ocr_batch_size}, max_retries: {max_retries}")
    
    try:
        # Update usecase status to In Progress
        logger.info("Updating usecase status to 'In Progress'")
        db = next(get_db())
        try:
            usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            if usecase:
                usecase.text_extraction = "In Progress"
                logger.info("Successfully updated usecase status to 'In Progress'")
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating usecase status to In Progress: {e}", exc_info=True)
            raise e
        finally:
            db.close()

        # Process files in batches
        total_files = len(ocr_data)
        logger.info(f"Processing {total_files} files in batches of {batch_size}")
        
        for i in range(0, total_files, batch_size):
            current_batch = ocr_data[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_files + batch_size - 1) // batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} with {len(current_batch)} files")
            run_parallel_ocr(current_batch, api_key, username, password, asset_id, num_workers, ocr_batch_size, max_retries)
            logger.info(f"Completed batch {batch_num}/{total_batches}")

        # Update status to Completed after successful processing
        logger.info("Updating usecase status to 'Completed'")
        db = next(get_db())
        try:
            usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            if usecase:
                usecase.text_extraction = "Completed"
                logger.info("Successfully updated usecase status to 'Completed'")
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating usecase status to Completed: {e}", exc_info=True)
            raise e
        finally:
            db.close()
        
        logger.info(f"OCR processing completed successfully for usecase: {usecase_id}")
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"OCR processing failed for usecase: {usecase_id}. Error: {e}", exc_info=True)
        
        # Update usecase status to Failed
        try:
            db = next(get_db())
            try:
                usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
                if usecase:
                    usecase.text_extraction = "Failed"
                    logger.info("Updated usecase status to 'Failed'")
                db.commit()
            except Exception as db_error:
                db.rollback()
                logger.error(f"Error updating usecase status to Failed: {db_error}", exc_info=True)
            finally:
                db.close()
        except Exception:
            logger.error("Failed to update usecase status to Failed", exc_info=True)
        
        raise e


