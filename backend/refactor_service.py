import re

with open('whatsapp_service.py', 'r', encoding='utf-8') as f:
    original = f.read()

# 1. Extract the resolve_img block
code_to_add = '''    async def resolve_media_to_base64(self, u: str) -> 'Optional[Tuple[str, str]]':
        """Return (base64_str, mime_type) for local files/remote URLs, or None on failure."""
        if not u:
            return None

        import base64 as _b64
        import os
        from pathlib import Path as _Path
        import httpx
        from urllib.parse import urlparse as _up
        
        _backend_dir = _Path(os.path.dirname(__file__))

        # --- Local file path ---
        _path_part = None
        if u.startswith('/uploads/') or u.startswith('uploads/'):
            _path_part = u.lstrip('/')
        elif u.startswith('http://') or u.startswith('https://'):
            _parsed = _up(u)
            _host = _parsed.netloc
            if 'localhost' in _host or '127.0.0.1' in _host or 'docker.internal' in _host:
                _path_part = _parsed.path.lstrip('/')
        else:
            _path_part = u.lstrip('/')

        if _path_part:
            _file = _backend_dir / _path_part
            if _file.exists():
                try:
                    _ext = _file.suffix.lower().replace('.', '') or 'jpeg'
                    _data = _b64.b64encode(_file.read_bytes()).decode()
                    logger.info(f"[resolve_media] local file → base64 ({_file.name})")
                    return (_data, f"image/{_ext}")
                except Exception as _re:
                    logger.warning(f"[resolve_media] Could not read local image {_file}: {_re}")
            else:
                _server_url = os.environ.get("SERVER_URL", "").rstrip("/")
                if _server_url:
                    _fallback_url = f"{_server_url}/{_path_part}"
                    logger.info(f"[resolve_media] local file missing, trying HTTP fallback: {_fallback_url}")
                    try:
                        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as _dl:
                            _r = await _dl.get(_fallback_url, headers={"User-Agent": "Mozilla/5.0"})
                        if _r.status_code == 200:
                            _ct = _r.headers.get("content-type", "image/jpeg")
                            _mime = _ct.split(";")[0].strip() or "image/jpeg"
                            _data = _b64.b64encode(_r.content).decode()
                            logger.info(f"[resolve_media] HTTP fallback downloaded → base64")
                            return (_data, _mime)
                        else:
                            logger.warning(f"[resolve_media] HTTP fallback failed: HTTP {_r.status_code}")
                    except Exception as _fbe:
                        logger.warning(f"[resolve_media] HTTP fallback exception: {_fbe}")

        # --- Remote URL (ImgBB, Cloudinary, S3, etc.) ---
        if u.startswith('http://') or u.startswith('https://'):
            _download_url = u
            if '.s3.' in u or '.s3-' in u or 's3.amazonaws.com' in u:
                try:
                    _parsed = _up(u)
                    _bucket = None
                    _key = None
                    _region = os.environ.get('AWS_REGION', 'us-east-1')

                    if '.s3.' in _parsed.netloc and '.amazonaws.com' in _parsed.netloc:
                        _parts = _parsed.netloc.split('.s3.')
                        _bucket = _parts[0]
                        _key = _parsed.path.lstrip('/')
                        if '.' in _parts[1]:
                            _region_part = _parts[1].split('.')[0]
                            if _region_part != 'amazonaws':
                                _region = _region_part

                    if _bucket and _key:
                        import boto3
                        _s3 = boto3.client('s3',
                            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                            region_name=_region
                        )
                        _download_url = _s3.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': _bucket, 'Key': _key},
                            ExpiresIn=3600
                        )
                except Exception as _s3e:
                    logger.warning(f"[resolve_media] Could not regenerate S3 URL: {_s3e}")
                
            try:
                async with httpx.AsyncClient(timeout=20, follow_redirects=True) as _dl:
                    _r = await _dl.get(_download_url, headers={"User-Agent": "Mozilla/5.0"})
                if _r.status_code == 200:
                    _ct = _r.headers.get("content-type", "image/jpeg")
                    _mime = _ct.split(";")[0].strip() or "image/jpeg"
                    _data = _b64.b64encode(_r.content).decode()
                    return (_data, _mime)
                else:
                    logger.warning(f"[resolve_media] Failed to dwl {_download_url[:100]}: HTTP {_r.status_code}")
            except Exception as _de:
                logger.warning(f"[resolve_media] Could not download image: {_de}")

        return None

'''

# Insert code_to_add before 'async def send_message'
with open('whatsapp_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for idx, l in enumerate(lines):
    if l.startswith('    async def send_message('):
        new_lines.append(code_to_add)
    new_lines.append(l)

new_content = "".join(new_lines)


# --- 2. Patch send_product_showcase ---
# Remove the inner _resolve_img definition completely
regex_del_resolve = re.compile(r'        async def _resolve_img\(u: str\):.*?        return None\n', re.DOTALL)
new_content = regex_del_resolve.sub('', new_content)

# Replace 'all_imgs = list(await asyncio.gather(*[_resolve_img(u) for u in all_imgs if u]))'
# with self.resolve_media_to_base64
new_content = new_content.replace(
    '_resolve_img(u) for u in all_imgs',
    'self.resolve_media_to_base64(u) for u in all_imgs'
)
# remove the unused imports right before the deleted block
new_content = new_content.replace('        import base64 as _b64\n        from pathlib import Path as _Path\n        _backend_dir = _Path(__file__).parent\n\n', '')


# --- 3. Patch send_message ---
target = """                        payload = {
                            "number": clean_to,
                            "mediatype": media_type or "image",
                            "media": media_url,
                            "caption": message,
                            "fileName": clean_filename,
                        }"""
replacement = """                        _resolved_media = None
                        if media_url:
                            _media_res = await self.resolve_media_to_base64(media_url)
                            if _media_res:
                                _base_64_str, _mime = _media_res
                                _resolved_media = f"data:{_mime};base64,{_base_64_str}"
                            else:
                                _resolved_media = media_url

                        # Send media message (FLAT structure fix)
                        payload = {
                            "number": clean_to,
                            "mediatype": media_type or "image",
                            "media": _resolved_media,
                            "caption": message,
                            "fileName": clean_filename,
                        }"""
new_content = new_content.replace(target, replacement)

with open('whatsapp_service.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
