import os
import uuid
from typing import List, Dict, Any
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

# Define a temporary or public folder to save PPTX files so the frontend can download them
# We'll put them in a public/media/presentations folder or similar. 
# For now, we'll save them to a local presentations dir and return the path/url.
PRESENTATIONS_DIR = os.path.join(os.getcwd(), "public", "presentations")

# Ensure the directory exists
os.makedirs(PRESENTATIONS_DIR, exist_ok=True)

def generate_presentation(title: str, slides_data: List[Dict[str, Any]], business_name: str = "My Business") -> Dict[str, Any]:
    """
    Generates a PowerPoint presentation (.pptx) and returns the public URL/path.
    
    slides_data format:
    [
        {"title": "Slide 1 Title", "content": ["Point 1", "Point 2"]},
        {"title": "Slide 2 Title", "content": ["Point A", "Point B"]}
    ]
    """
    try:
        prs = Presentation()
        
        # Slide 1: Title Slide
        title_slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_slide_layout)
        title_shape = slide.shapes.title
        subtitle_shape = slide.placeholders[1]
        
        title_shape.text = title
        subtitle_shape.text = f"Presented by {business_name}"
        
        # Style Title
        for paragraph in title_shape.text_frame.paragraphs:
            paragraph.font.bold = True
            paragraph.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
            
        # Add content slides
        bullet_slide_layout = prs.slide_layouts[1]
        for slide_data in slides_data:
            slide = prs.slides.add_slide(bullet_slide_layout)
            shapes = slide.shapes
            
            title_shape = shapes.title
            body_shape = shapes.placeholders[1]
            
            title_shape.text = slide_data.get("title", "Slide")
            
            tf = body_shape.text_frame
            content_items = slide_data.get("content", [])
            
            for i, point in enumerate(content_items):
                if i == 0:
                    p = tf.paragraphs[0]
                    p.text = point
                else:
                    p = tf.add_paragraph()
                    p.text = point
                p.level = 0
                p.font.size = Pt(24)
                
        # Save the file
        filename = f"presentation_{uuid.uuid4().hex[:8]}.pptx"
        filepath = os.path.join(PRESENTATIONS_DIR, filename)
        prs.save(filepath)
        
        # Return a relative URL that can be accessed by the frontend (assuming /public is served or mapped)
        # Assuming the backend serves the 'public' directory at some endpoint, or we can just return the local file path
        # For Zilo, the backend usually runs on port 8000. If we need to serve it, we might need a dedicated route, 
        # or we just return the path so the agent can tell the user where it is.
        download_url = f"/api/media/presentations/{filename}" # We'll need to ensure this route exists or we use an existing one
        
        return {
            "success": True,
            "filename": filename,
            "filepath": filepath,
            "url": download_url
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
