"""
Product Image Upload Handler
Handles multiple image uploads and storage for product catalog
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import List, Dict
from fastapi import UploadFile
import logging

logger = logging.getLogger(__name__)

# Upload directory
UPLOAD_DIR = Path(__file__).parent / "uploads" / "products"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
