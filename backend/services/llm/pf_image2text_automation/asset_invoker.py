import asyncio
import io
import os
import aiohttp


class AssetInvoker:
    def __init__(self, api_key, username, password, asset_id):
        self.api_key = api_key
        self.username = username
        self.password = password
        self.asset_id = asset_id

        self.headers_QA = {
            'apikey': self.api_key,
            'username': self.username,
            'password': self.password
        }

    async def get_access_token(self):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.intellectseecstag.com/accesstoken/idxpigtb", headers=self.headers_QA) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('access_token', '')
                return ""

    async def asset_post(self, asset_headers, asset_payload, files):
        url = "https://api.intellectseecstag.com/magicplatform/v1/invokeasset/" + self.asset_id + "/genai"
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            for field, file_info in files:
                filename, file_obj, content_type = file_info
                form.add_field(field, file_obj, filename=filename, content_type=content_type)
            async with session.post(url, headers=asset_headers, data=form) as response:
                json_response = await response.json()
                trace_id = json_response["trace_id"]
                return trace_id

    async def get_chunks(self, asset_headers, trace_id):
        status = ""
        async with aiohttp.ClientSession() as session:
            while status != "COMPLETED":
                url = "https://api.intellectseecstag.com/magicplatform/v1/invokeasset/" + self.asset_id + "/" + trace_id
                async with session.get(url, headers=asset_headers) as response:
                    data = await response.json()
                try:
                    if data.get('error_code') == "GenaiBaseException":
                        raise Exception(data.get('error_description'))
                except Exception:
                    pass
                await asyncio.sleep(2)
                status = data.get('status', "")
                if status == "COMPLETED":
                    return data

    async def _invoke_asset_internal(self, filepaths):
        access_token = await self.get_access_token()
        asset_headers = {
            'Accept': 'application/json',
            'apikey': self.api_key,
            'Authorization': 'Bearer ' + access_token,
        }
        asset_payload = {}
        files = []
        for fp in filepaths:
            with open(fp, 'rb') as f:
                file_bytes = f.read()
            file_obj = io.BytesIO(file_bytes)
            file_obj.seek(0)
            files.append(('Image', (os.path.basename(fp), file_obj, 'image/jpeg')))
        trace_id = await self.asset_post(asset_headers, asset_payload, files)
        output = await self.get_chunks(asset_headers, trace_id)
        responses = [entry["debug_logs"][0]["raw_response"] for entry in output["response"]["output"]]
        return responses

    async def invoke_asset(self, filepaths):
        return await asyncio.wait_for(self._invoke_asset_internal(filepaths), timeout=400)


