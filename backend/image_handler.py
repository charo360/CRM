"""
Product Image Upload Handler
Handles multiple image uploads and storage for product catalog
Supports both local storage and Cloudinary for public URLs
"""
import os
import uuid
import aiofiles
import base64
import httpx
from pathlib import Path
from typing import List, Dict, Optional
from fastapi import UploadFile
import logging

logger = logging.getLogger(__name__)

# Upload directory
UPLOAD_DIR = Path(__file__).parent / "uploads" / "products"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Cloudinary config - loaded dynamically to ensure .env is loaded first
def get_cloudinary_config():
    """Get Cloudinary config, stripping any whitespace from env vars"""
    return {
        'cloud_name': os.environ.get('CLOUDINARY_CLOUD_NAME', '').strip(),
        'api_key': os.environ.get('CLOUDINARY_API_KEY', '').strip(),
        'api_secret': os.environ.get('CLOUDINARY_API_SECRET', '').strip(),
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
        Save uploaded image to disk
        
        Args:
            file: Uploaded file
            
        Returns:
            Dict with image_url and filename
        """
        try:
            # Validate file type
            if not ImageUploadHandler.is_allowed_file(file.filename):
                raise ValueError(f"File type not allowed. Allowed: {ALLOWED_EXTENSIONS}")
            
            # Generate unique filename
            ext = Path(file.filename).suffix.lower()
            unique_filename = f"{uuid.uuid4()}{ext}"
            file_path = UPLOAD_DIR / unique_filename
            
            # Read file content
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB")
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            # Return URL (relative path)
            image_url = f"/uploads/products/{unique_filename}"
            
            logger.info(f"Saved image: {unique_filename}")
            
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
            
            # Check if Cloudinary is configured
            if not CLOUDINARY_CLOUD_NAME or not CLOUDINARY_API_KEY or not CLOUDINARY_API_SECRET:
                # Fallback: save locally and return local path
                logger.warning("Cloudinary not configured, saving locally")
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
            logger.error(f"Error uploading to Cloudinary: {e}")
            raise
    
    @staticmethod
    async def upload_base64_to_cloudinary(base64_data: str, filename: str = "image.jpg") -> Dict[str, str]:
        """
        Upload base64 image data to Cloudinary
        
        Args:
            base64_data: Base64 encoded image data (with or without data URI prefix)
            filename: Original filename for extension detection
            
        Returns:
            Dict with public image_url
        """
        try:
            # Get Cloudinary config dynamically
            config = get_cloudinary_config()
            cloud_name = config['cloud_name']
            api_key = config['api_key']
            api_secret = config['api_secret']
            
            # Check if Cloudinary is configured
            logger.info(f"Cloudinary config check - Cloud: {bool(cloud_name)}, Key: {bool(api_key)}, Secret: {bool(api_secret)}")
            if not cloud_name or not api_key or not api_secret:
                raise ValueError(f"Cloudinary not configured. Cloud: {cloud_name}, Key: {api_key[:4] if api_key else 'None'}...")
            
            # Ensure data URI format
            if not base64_data.startswith('data:'):
                ext = Path(filename).suffix.lower().replace('.', '') or 'jpeg'
                base64_data = f"data:image/{ext};base64,{base64_data}"
            
            # Upload to Cloudinary
            import hashlib
            import time
            
            timestamp = str(int(time.time()))
            params_to_sign = f"folder=broadcasts&timestamp={timestamp}{api_secret}"
            signature = hashlib.sha1(params_to_sign.encode()).hexdigest()
            
            logger.info(f"Uploading to Cloudinary cloud: {cloud_name}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
                    data={
                        "file": base64_data,
                        "api_key": api_key,
                        "timestamp": timestamp,
                        "signature": signature,
                        "folder": "broadcasts"
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    image_url = result.get("secure_url", result.get("url"))
                    logger.info(f"Uploaded base64 to Cloudinary: {image_url}")
                    return {
                        "image_url": image_url,
                        "public_id": result.get("public_id"),
                        "filename": filename
                    }
                else:
                    logger.error(f"Cloudinary upload failed: {response.text}")
                    raise ValueError(f"Upload failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Error uploading base64 to Cloudinary: {e}")
            raise
