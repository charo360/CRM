"""
Product Image Upload Handler
Handles multiple image uploads and storage for product catalog
Supports both local storage and Cloudinary for public URLs
"""
import os
import uuid
import aiofiles
import base64
import time
from pathlib import Path
from typing import List, Dict, Optional
from fastapi import UploadFile
import logging
import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)

# Upload directory
UPLOAD_DIR = Path(__file__).parent / "uploads" / "products"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Cloudinary config - loaded dynamically to ensure .env is loaded first
def get_cloudinary_config():
    """Get Cloudinary config, stripping any whitespace from env vars"""
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '').strip()
    api_key = os.environ.get('CLOUDINARY_API_KEY', '').strip()
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', '').strip()
    
    # Configure cloudinary
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )
    
    return {
        'cloud_name': cloud_name,
        'api_key': api_key,
        'api_secret': api_secret,
    }

# Allowed image types
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class ImageUploadHandler:
    """Handle product image uploads"""
    
    @staticmethod
    def is_allowed_file(filename: str) -> bool:
        """Check if file extension is allowed"""
        ext = Path(filename).suffix.lower()
        return ext in ALLOWED_EXTENSIONS
    
    @staticmethod
    async def save_image(file: UploadFile) -> Dict[str, str]:
        """
        Save uploaded image - uses cloud storage (ImgBB/S3) if configured, otherwise local disk
        
        Args:
            file: Uploaded file
            
        Returns:
            Dict with image_url and filename
        """
        try:
            # Validate file type
            if not ImageUploadHandler.is_allowed_file(file.filename):
                raise ValueError(f"File type not allowed. Allowed: {ALLOWED_EXTENSIONS}")
            
            # Read file content
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB")
            
            # Try cloud storage first (for Render deployment)
            # Check AWS S3
            aws_key = os.environ.get('AWS_ACCESS_KEY_ID')
            aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY')
            aws_bucket = os.environ.get('AWS_BUCKET_NAME')
            
            if aws_key and aws_secret and aws_bucket and S3Handler.should_attempt_upload():
                try:
                    logger.info("Using AWS S3 for product image")
                    base64_data = base64.b64encode(content).decode('utf-8')
                    s3_url = await S3Handler.upload_file(base64_data, file.filename)
                    return {
                        "image_url": s3_url,
                        "filename": file.filename
                    }
                except Exception as s3_error:
                    # An expired or rotated AWS key must not stop merchants
                    # uploading product photos when the configured backup image
                    # service is healthy.
                    S3Handler.pause_upload_attempts()
                    logger.warning("S3 product image upload failed; trying backup storage: %s", s3_error)
            
            # Check ImgBB
            imgbb_key = os.environ.get('IMGBB_API_KEY')
            if imgbb_key:
                logger.info("Using ImgBB for product image")
                base64_data = base64.b64encode(content).decode('utf-8')
                result = await ImageUploadHandler.upload_base64_to_cloudinary(base64_data, file.filename)
                return {
                    "image_url": result["image_url"],
                    "filename": file.filename
                }
            
            # Fallback: Save locally (for local development)
            logger.warning("No cloud storage configured, saving locally")
            ext = Path(file.filename).suffix.lower()
            unique_filename = f"{uuid.uuid4()}{ext}"
            file_path = UPLOAD_DIR / unique_filename
            
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            image_url = f"/uploads/products/{unique_filename}"
            logger.info(f"Saved image locally: {unique_filename}")
            
            return {
                "image_url": image_url,
                "filename": unique_filename
            }
            
        except Exception as e:
            logger.error(f"Error saving image: {e}")
            raise
    
    @staticmethod
    async def save_multiple_images(files: List[UploadFile]) -> List[Dict[str, str]]:
        """
        Save multiple uploaded images
        
        Args:
            files: List of uploaded files
            
        Returns:
            List of dicts with image_url and filename
        """
        results = []
        
        for file in files:
            try:
                result = await ImageUploadHandler.save_image(file)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to save {file.filename}: {e}")
                # Continue with other files
                results.append({
                    "error": str(e),
                    "filename": file.filename
                })
        
        return results
    
    @staticmethod
    def delete_image(filename: str) -> bool:
        """
        Delete an image file
        
        Args:
            filename: Name of file to delete
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            file_path = UPLOAD_DIR / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted image: {filename}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting image {filename}: {e}")
            return False
    
    @staticmethod
    def get_image_path(filename: str) -> Path:
        """Get full path to image file"""
        return UPLOAD_DIR / filename
    
    @staticmethod
    async def upload_to_cloudinary(file: UploadFile) -> Dict[str, str]:
        """
        Upload image to Cloudinary for public URL access
        Used for broadcast images that need to be accessible by WhatsApp/Twilio
        
        Args:
            file: Uploaded file
            
        Returns:
            Dict with public image_url
        """
        try:
            # Validate file type
            if not ImageUploadHandler.is_allowed_file(file.filename):
                raise ValueError(f"File type not allowed. Allowed: {ALLOWED_EXTENSIONS}")
            
            # Read file content
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB")
            
            # Check if AWS S3 is configured (Priority)
            aws_key = os.environ.get('AWS_ACCESS_KEY_ID')
            aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY')
            aws_bucket = os.environ.get('AWS_BUCKET_NAME')
            
            if aws_key and aws_secret and aws_bucket and S3Handler.should_attempt_upload():
                try:
                    logger.info("AWS S3 Configured, using S3 for upload")
                    # Convert upload file to base64 for S3Handler compatible input
                    await file.seek(0)
                    content = await file.read()
                    base64_data = base64.b64encode(content).decode('utf-8')

                    # Upload to S3
                    s3_url = await S3Handler.upload_file(base64_data, file.filename)

                    return {
                        "image_url": s3_url,
                        "public_id": str(uuid.uuid4()), # Mock public_id for S3
                        "filename": file.filename
                    }
                except Exception as s3_error:
                    S3Handler.pause_upload_attempts()
                    logger.warning("S3 image upload failed; trying configured backup storage: %s", s3_error)

            # Check if Cloudinary is configured
            cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '').strip()
            api_key = os.environ.get('CLOUDINARY_API_KEY', '').strip()
            api_secret = os.environ.get('CLOUDINARY_API_SECRET', '').strip()
            
            if not cloud_name or not api_key or not api_secret:
                # Check for ImgBB Fallback
                imgbb_key = os.environ.get('IMGBB_API_KEY')
                if imgbb_key:
                    logger.info("Cloudinary not configured, falling back to ImgBB")
                    # Convert upload file to base64
                    await file.seek(0)
                    content = await file.read()
                    base64_data = base64.b64encode(content).decode('utf-8')
                    # Call ImgBB uploader
                    return await ImageUploadHandler.upload_base64_to_cloudinary(base64_data, file.filename)
                
                # Fallback: save locally and return local path
                logger.warning("Cloudinary/ImgBB/AWS not configured, saving locally")
                await file.seek(0)  # Reset file position
                return await ImageUploadHandler.save_image(file)
            
            # Convert to base64
            base64_image = base64.b64encode(content).decode('utf-8')
            ext = Path(file.filename).suffix.lower().replace('.', '')
            data_uri = f"data:image/{ext};base64,{base64_image}"
            
            # Upload to Cloudinary
            import hashlib
            import time
            
            timestamp = str(int(time.time()))
            params_to_sign = f"timestamp={timestamp}{CLOUDINARY_API_SECRET}"
            signature = hashlib.sha1(params_to_sign.encode()).hexdigest()
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload",
                    data={
                        "file": data_uri,
                        "api_key": CLOUDINARY_API_KEY,
                        "timestamp": timestamp,
                        "signature": signature,
                        "folder": "broadcasts"
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    image_url = result.get("secure_url", result.get("url"))
                    logger.info(f"Uploaded to Cloudinary: {image_url}")
                    return {
                        "image_url": image_url,
                        "public_id": result.get("public_id"),
                        "filename": file.filename
                    }
                else:
                    logger.error(f"Cloudinary upload failed: {response.text}")
                    raise ValueError(f"Upload failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            raise
    

    @staticmethod
    async def upload_base64_to_cloudinary(base64_data: str, filename: str = "image.jpg") -> Dict[str, str]:
        """
        Upload base64 image data to ImgBB (Free Alternative)
        Kept name 'upload_base64_to_cloudinary' to avoid breaking callers, but uses ImgBB.
        
        Args:
            base64_data: Base64 encoded image data
            filename: Original filename
            
        Returns:
            Dict with public image_url
        """
        try:
            # Get ImgBB API Key
            # We will use the existing env var or a new one
            api_key = os.environ.get('IMGBB_API_KEY')
            if not api_key:
                # Fallback to Cloudinary var if user put the key there, or error
                api_key = os.environ.get('CLOUDINARY_API_KEY')
            
            if not api_key:
                 raise ValueError("IMGBB_API_KEY not found in environment")

            # Strip header if present, ImgBB expects just the base64 string or the file
            # But the API handles base64 parameter including headers usually.
            # Let's clean it just in case:
            if base64_data.startswith('data:'):
                base64_data = base64_data.split(',')[1]

            logger.info(f"Uploading to ImgBB...")
            
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.imgbb.com/1/upload",
                    data={
                        "key": api_key,
                        "image": base64_data,
                        "name": Path(filename).stem
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    image_url = result['data']['url']
                    logger.info(f"Uploaded to ImgBB: {image_url}")
                    
                    return {
                        "image_url": image_url,
                        "public_id": result['data']['id'],
                        "filename": filename
                    }
                else:
                    logger.error(f"ImgBB upload failed: {response.text}")
                    raise ValueError(f"ImgBB Upload failed: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"Error uploading to ImgBB: {e}")
            raise


class S3Handler:
    """Handle AWS S3 Image Uploads"""

    # Avoid making every merchant wait on the same broken credentials. A single
    # failed upload switches the process to the configured backup host for a
    # short period, then retries S3 later in case credentials were fixed.
    _retry_s3_after = 0.0
    _s3_backoff_seconds = 600

    @classmethod
    def should_attempt_upload(cls) -> bool:
        return time.monotonic() >= cls._retry_s3_after

    @classmethod
    def pause_upload_attempts(cls) -> None:
        cls._retry_s3_after = time.monotonic() + cls._s3_backoff_seconds
    
    @staticmethod
    def get_s3_client():
        import boto3
        from botocore.config import Config
        try:
            region = os.environ.get('AWS_REGION', 'us-east-1')
            return boto3.client(
                's3',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                region_name=region,
                config=Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'virtual'},
                    # A bad key should fail quickly and allow the backup image
                    # service to handle the upload instead of blocking the app.
                    connect_timeout=3,
                    read_timeout=8,
                    retries={'max_attempts': 1, 'mode': 'standard'},
                ),
            )
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise

    @staticmethod
    async def upload_file(base64_data: str, filename: str, content_type: str = "image/jpeg", folder: str = "products") -> str:
        """
        Upload base64 image to S3 bucket
        Returns: Public URL
        """
        try:
            bucket_name = os.environ.get('AWS_BUCKET_NAME')
            if not bucket_name:
                raise ValueError("AWS_BUCKET_NAME not set in .env")

            # Decode base64
            if "," in base64_data:
                header, encoded = base64_data.split(",", 1)
                # Try to guess extension/content-type from header data:image/png;base64
                if "image/png" in header:
                    content_type = "image/png"
                    if not filename.endswith(".png"): filename += ".png"
                elif "image/jpeg" in header:
                    content_type = "image/jpeg"
                    if not filename.endswith(".jpg") and not filename.endswith(".jpeg"): filename += ".jpg"
                base64_data = encoded
            
            import base64
            file_content = base64.b64decode(base64_data)
            
            # Use threading to run blocking boto3 call
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Unique filename
            key = f"{folder.rstrip('/')}/{uuid.uuid4()}-{filename}"
            
            def _upload():
                s3 = S3Handler.get_s3_client()
                # Upload without ACL (bucket might block public ACLs)
                s3.put_object(
                    Bucket=bucket_name,
                    Key=key,
                    Body=file_content,
                    ContentType=content_type
                )
                return key

            key = await loop.run_in_executor(None, _upload)
            url = S3Handler.stable_public_url_for_key(key)
            logger.info(f"Uploaded to S3: {key} → {url}")
            return url

        except Exception as e:
            logger.error(f"S3 Upload Error: {e}")
            raise

    @staticmethod
    def _public_base_url() -> str:
        return (
            os.environ.get("BACKEND_PUBLIC_URL")
            or os.environ.get("PUBLIC_BASE_URL")
            or os.environ.get("SERVER_URL")
            or os.environ.get("WEBHOOK_BASE_URL")
            or ""
        ).rstrip("/")

    @staticmethod
    def stable_public_url_for_key(key: str) -> str:
        """Permanent URL via server-side S3 proxy — does not expire like presigned URLs."""
        key = (key or "").lstrip("/")
        if not key:
            return ""
        path = f"/api/images/s3/{key}"
        base = S3Handler._public_base_url()
        return f"{base}{path}" if base else path

    @staticmethod
    def resolve_accessible_url(url: str) -> str:
        """Return a non-expiring fetchable URL for stored media (logos, product images, etc.)."""
        url = (url or "").strip()
        if not url:
            return url
        if url.startswith("/api/images/s3/"):
            base = S3Handler._public_base_url()
            return f"{base}{url}" if base else url
        if url.startswith("/uploads/"):
            base = S3Handler._public_base_url()
            return f"{base}{url}" if base else url
        bucket, key = S3Handler.parse_s3_source_to_bucket_key(url)
        if key:
            return S3Handler.stable_public_url_for_key(key)
        if url.startswith("http://") or url.startswith("https://"):
            return url
        base = S3Handler._public_base_url()
        if base:
            return f"{base}{url if url.startswith('/') else '/' + url}"
        return url

    @staticmethod
    def parse_s3_source_to_bucket_key(url: str) -> tuple:
        """Parse an S3 URL (virtual-hosted, path-style, or presigned) into (bucket, key).

        Handles:
          https://<bucket>.s3.amazonaws.com/<key>
          https://<bucket>.s3.<region>.amazonaws.com/<key>
          https://s3.<region>.amazonaws.com/<bucket>/<key>
          https://s3.amazonaws.com/<bucket>/<key>
        Presigned query parameters are stripped automatically.
        Returns (bucket, key) or ("", "") if not parseable.
        """
        import re as _re
        from urllib.parse import urlparse as _urlparse
        if not url or "amazonaws.com" not in url:
            return ("", "")
        try:
            p = _urlparse(url)
            host = p.hostname or ""
            # Strip presigned query string — path is all we need
            path = p.path.lstrip("/")

            # Virtual-hosted style: <bucket>.s3[.<region>].amazonaws.com/<key>
            m = _re.match(r"^(.+?)\.s3(?:\.[^.]+)?\.amazonaws\.com$", host)
            if m:
                return (m.group(1), path)

            # Path-style: s3[.<region>].amazonaws.com/<bucket>/<key>
            m2 = _re.match(r"^s3(?:\.[^.]+)?\.amazonaws\.com$", host)
            if m2 and "/" in path:
                bucket_part, _, key_part = path.partition("/")
                return (bucket_part, key_part)
        except Exception:
            pass
        return ("", "")

    @staticmethod
    def generate_presigned_get_url(bucket: str, key: str, expires_in: int = 3600) -> str:
        """Generate a pre-signed GET URL for an S3 object."""
        s3 = S3Handler.get_s3_client()
        return s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expires_in,
        )

    @staticmethod
    async def async_generate_presigned_get_url(bucket: str, key: str, expires_in: int = 3600) -> str:
        """Async wrapper around generate_presigned_get_url."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: S3Handler.generate_presigned_get_url(bucket, key, expires_in),
        )
