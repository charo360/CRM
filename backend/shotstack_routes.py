"""
Shotstack API router — image/voice generation to complement Kling AI.
Focuses on:
- Image generation (posters/thumbnails) from templates
- Voice synthesis (text-to-speech) with multiple voices  
- Combined templates that generate both image and voice assets
- Works alongside Kling AI for video generation
"""

import os, uuid, httpx, logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

def make_shotstack_router(user_dep):
    router = APIRouter(prefix="/shotstack", tags=["shotstack"])
    
    # ── Config ────────────────────────────────────────────────────────────────
    SHOTSTACK_API_KEY = os.getenv("SHOTSTACK_API_KEY")
    SHOTSTACK_API_URL = os.getenv("SHOTSTACK_API_URL", "https://api.shotstack.io/v1")
    
    if not SHOTSTACK_API_KEY:
        logging.warning("[shotstack] SHOTSTACK_API_KEY not set — endpoints will return mock responses")
    
    # ── Models ────────────────────────────────────────────────────────────────
    
    class Asset(BaseModel):
        type: str = Field(..., description="Asset type: image, video, title, audio, voice")
        src: Optional[str] = Field(None, description="URL or file reference")
        text: Optional[str] = Field(None, description="Text for title/voice assets")
        style: Optional[Dict[str, Any]] = Field(None, description="Style options")
        start: Optional[float] = Field(0, description="Start time in seconds")
        length: Optional[float] = Field(None, description="Duration in seconds")
        position: Optional[str] = Field("center", description="Position for overlays")
        transition: Optional[Dict[str, Any]] = Field(None, description="Transition effects")
    
    class ShotstackTemplate(BaseModel):
        id: Optional[str] = Field(None, description="Template ID (omit for new)")
        name: str = Field(..., description="Template name")
        description: Optional[str] = Field(None)
        type: str = Field("image", description="Output type: image, voice, combined")
        format: str = Field("png", description="Output format: jpg, png, mp3")
        dimensions: Dict[str, int] = Field({"width": 1920, "height": 1080}, description="Output dimensions")
        duration: Optional[float] = Field(None, description="Duration for voice assets")
        assets: List[Asset] = Field(default_factory=list, description="Design assets")
        voice: Optional[Dict[str, Any]] = Field(None, description="Voice synthesis settings")
        background: Optional[str] = Field(None, description="Background color/image")
        music: Optional[str] = Field(None, description="Background music URL")
        
    class RenderRequest(BaseModel):
        template_id: Optional[str] = Field(None, description="Template ID to render")
        template: Optional[ShotstackTemplate] = Field(None, description="Inline template")
        modifications: Dict[str, Any] = Field(default_factory=dict, description="Field overrides")
        output_format: Optional[str] = Field(None, description="Override output format")
        webhook_url: Optional[str] = Field(None, description="Webhook for completion")
        
    class RenderResponse(BaseModel):
        id: str
        status: str
        message: Optional[str] = None
        render_url: Optional[str] = None
        expires_at: Optional[str] = None
    
    # ── Helpers ───────────────────────────────────────────────────────────────
    
    async def _shotstack_request(method: str, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Shotstack API."""
        if not SHOTSTACK_API_KEY:
            # Mock response for development
            return {
                "response": {
                    "id": str(uuid.uuid4()),
                    "status": "queued",
                    "message": "Mock render queued (SHOTSTACK_API_KEY not set)"
                }
            }
        
        headers = {
            "x-api-key": SHOTSTACK_API_KEY,
            "content-type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            if method.upper() == "GET":
                r = await client.get(f"{SHOTSTACK_API_URL}/{endpoint}", headers=headers)
            else:
                r = await client.post(f"{SHOTSTACK_API_URL}/{endpoint}", headers=headers, json=data)
            
            if r.status_code >= 400:
                raise HTTPException(r.status_code, f"Shotstack API error: {r.text}")
            
            return r.json()
    
    def _build_shotstack_timeline(template: ShotstackTemplate, modifications: Dict[str, Any]) -> Dict[str, Any]:
        """Convert our template to Shotstack timeline format."""
        timeline = {
            "output": {
                "format": template.format,
                "resolution": template.dimensions,
                "quality": "medium"
            },
            "timeline": {
                "soundtrack": None,
                "tracks": []
            }
        }
        
        # Apply modifications
        if modifications:
            template_dict = template.dict()
            template_dict.update(modifications)
            template = ShotstackTemplate(**template_dict)
        
        # Background
        if template.background:
            bg_clip = {
                "asset": {
                    "type": "image" if template.background.startswith(("http", "/")) else "color",
                    "src": template.background
                },
                "start": 0,
                "length": template.duration or 5,
                "fit": "cover"
            }
            timeline["timeline"]["tracks"].append({
                "clips": [bg_clip]
            })
        
        # Voice synthesis
        if template.voice:
            voice_text = template.voice.get("text", "")
            if voice_text:
                voice_asset = {
                    "type": "audio",
                    "src": f"tts:{template.voice.get('voice', 'samantha')}",
                    "text": voice_text,
                    "effect": template.voice.get("effect", "volume:0.8")
                }
                voice_clip = {
                    "asset": voice_asset,
                    "start": template.voice.get("start", 0),
                    "length": template.voice.get("length", template.duration or 5)
                }
                if not timeline["timeline"]["soundtrack"]:
                    timeline["timeline"]["soundtrack"] = {"tracks": []}
                timeline["timeline"]["soundtrack"]["tracks"].append({"clips": [voice_clip]})
        
        # Process assets
        for i, asset in enumerate(template.assets):
            clip = {
                "start": asset.start,
                "length": asset.length or (template.duration or 5) / len(template.assets)
            }
            
            if asset.type == "title":
                clip["asset"] = {
                    "type": "title",
                    "text": asset.text or "",
                    "style": asset.style or {
                        "fontSize": "48px",
                        "fontFamily": "Montserrat",
                        "backgroundColor": "#00000000",
                        "color": "#ffffff"
                    }
                }
                if asset.position:
                    clip["position"] = asset.position
            elif asset.type == "image":
                clip["asset"] = {
                    "type": "image",
                    "src": asset.src or ""
                }
                clip["fit"] = "cover"
                if asset.position != "center":
                    clip["position"] = asset.position
            elif asset.type == "video":
                clip["asset"] = {
                    "type": "video",
                    "src": asset.src or ""
                }
            elif asset.type == "audio":
                clip["asset"] = {
                    "type": "audio",
                    "src": asset.src or ""
                }
                if not timeline["timeline"]["soundtrack"]:
                    timeline["timeline"]["soundtrack"] = {"tracks": []}
                timeline["timeline"]["soundtrack"]["tracks"].append({"clips": [clip]})
                continue
            
            # Add to appropriate track
            track_index = i % 4  # Distribute across 4 tracks
            while len(timeline["timeline"]["tracks"]) <= track_index:
                timeline["timeline"]["tracks"].append({"clips": []})
            timeline["timeline"]["tracks"][track_index]["clips"].append(clip)
        
        # Background music
        if template.music:
            if not timeline["timeline"]["soundtrack"]:
                timeline["timeline"]["soundtrack"] = {"tracks": []}
            music_clip = {
                "asset": {
                    "type": "audio",
                    "src": template.music,
                    "effect": "volume:0.3"
                },
                "start": 0,
                "length": template.duration or 5
            }
            timeline["timeline"]["soundtrack"]["tracks"].append({"clips": [music_clip]})
        
        return timeline
    
    # ── Routes ────────────────────────────────────────────────────────────────
    
    @router.post("/templates", response_model=Dict[str, Any])
    async def create_template(template: ShotstackTemplate, user=Depends(user_dep)):
        """Create a new Shotstack template."""
        user_id = user.get("business_id", user["_id"])
        
        doc = template.dict()
        doc["_id"] = str(uuid.uuid4())
        doc["user_id"] = user_id
        doc["created_at"] = datetime.utcnow()
        doc["updated_at"] = datetime.utcnow()
        
        # Store in MongoDB (assuming db is available globally or passed)
        from server import db
        await db.shotstack_templates.insert_one(doc)
        
        return {"template": doc}
    
    @router.get("/templates", response_model=Dict[str, Any])
    async def list_templates(type: Optional[str] = None, user=Depends(user_dep)):
        """List user's Shotstack templates."""
        user_id = user.get("business_id", user["_id"])
        
        filter_dict = {"user_id": user_id}
        if type:
            filter_dict["type"] = type
        
        from server import db
        templates = await db.shotstack_templates.find(filter_dict).sort("created_at", -1).to_list(100)
        
        return {"templates": templates}
    
    @router.get("/templates/{template_id}", response_model=Dict[str, Any])
    async def get_template(template_id: str, user=Depends(user_dep)):
        """Get a specific template."""
        user_id = user.get("business_id", user["_id"])
        
        from server import db
        template = await db.shotstack_templates.find_one({"_id": template_id, "user_id": user_id})
        if not template:
            raise HTTPException(404, "Template not found")
        
        return {"template": template}
    
    @router.put("/templates/{template_id}", response_model=Dict[str, Any])
    async def update_template(template_id: str, template: ShotstackTemplate, user=Depends(user_dep)):
        """Update a template."""
        user_id = user.get("business_id", user["_id"])
        
        from server import db
        existing = await db.shotstack_templates.find_one({"_id": template_id, "user_id": user_id})
        if not existing:
            raise HTTPException(404, "Template not found")
        
        doc = template.dict()
        doc["updated_at"] = datetime.utcnow()
        
        await db.shotstack_templates.update_one(
            {"_id": template_id},
            {"$set": doc}
        )
        
        return {"template": {**existing, **doc}}
    
    @router.delete("/templates/{template_id}", response_model=Dict[str, Any])
    async def delete_template(template_id: str, user=Depends(user_dep)):
        """Delete a template."""
        user_id = user.get("business_id", user["_id"])
        
        from server import db
        result = await db.shotstack_templates.delete_one({"_id": template_id, "user_id": user_id})
        if result.deleted_count == 0:
            raise HTTPException(404, "Template not found")
        
        return {"status": "deleted", "id": template_id}
    
    @router.post("/render", response_model=RenderResponse)
    async def render(request: RenderRequest, user=Depends(user_dep)):
        """Render a template with modifications."""
        user_id = user.get("business_id", user["_id"])
        
        # Get template
        if request.template_id:
            from server import db
            template_doc = await db.shotstack_templates.find_one({"_id": request.template_id, "user_id": user_id})
            if not template_doc:
                raise HTTPException(404, "Template not found")
            template = ShotstackTemplate(**template_doc)
        elif request.template:
            template = request.template
        else:
            raise HTTPException(400, "Either template_id or template is required")
        
        # Build Shotstack timeline
        timeline = _build_shotstack_timeline(template, request.modifications)
        
        # Override output format if specified
        if request.output_format:
            timeline["output"]["format"] = request.output_format
        
        # Add webhook if provided
        if request.webhook_url:
            timeline["output"]["webhook"] = {"url": request.webhook_url}
        
        # Submit to Shotstack
        try:
            response = await _shotstack_request("POST", "render", timeline)
            render_id = response.get("response", {}).get("id")
            
            # Store render job
            job_doc = {
                "_id": render_id,
                "user_id": user_id,
                "template_id": request.template_id,
                "template_name": template.name,
                "status": "queued",
                "timeline": timeline,
                "created_at": datetime.utcnow(),
                "webhook_url": request.webhook_url
            }
            
            from server import db
            await db.shotstack_renders.insert_one(job_doc)
            
            return RenderResponse(
                id=render_id,
                status="queued",
                message="Render job submitted successfully"
            )
            
        except Exception as e:
            logging.error(f"[shotstack] Render failed: {e}")
            raise HTTPException(500, f"Render failed: {str(e)}")
    
    @router.get("/render/{render_id}", response_model=Dict[str, Any])
    async def get_render_status(render_id: str, user=Depends(user_dep)):
        """Get render job status and result URL."""
        user_id = user.get("business_id", user["_id"])
        
        # Check local job first
        from server import db
        job = await db.shotstack_renders.find_one({"_id": render_id, "user_id": user_id})
        if not job:
            raise HTTPException(404, "Render job not found")
        
        # If still queued/in-progress, check Shotstack
        if job.get("status") in ("queued", "rendering"):
            try:
                response = await _shotstack_request("GET", f"render/{render_id}")
                shotstack_status = response.get("response", {}).get("status")
                
                # Update local status
                await db.shotstack_renders.update_one(
                    {"_id": render_id},
                    {"$set": {
                        "status": shotstack_status,
                        "updated_at": datetime.utcnow(),
                        "shotstack_response": response
                    }}
                )
                
                job["status"] = shotstack_status
                job["shotstack_response"] = response
                
            except Exception as e:
                logging.error(f"[shotstack] Status check failed: {e}")
        
        # If completed, get render URL
        render_url = None
        expires_at = None
        if job.get("status") == "done":
            try:
                response = await _shotstack_request("GET", f"render/{render_id}")
                render_url = response.get("response", {}).get("url")
                expires_at = response.get("response", {}).get("expires")
            except Exception as e:
                logging.error(f"[shotstack] Failed to get render URL: {e}")
        
        return {
            "id": render_id,
            "status": job.get("status"),
            "template_name": job.get("template_name"),
            "render_url": render_url,
            "expires_at": expires_at,
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at")
        }
    
    @router.get("/renders", response_model=Dict[str, Any])
    async def list_renders(limit: int = 50, status: Optional[str] = None, user=Depends(user_dep)):
        """List user's render jobs."""
        user_id = user.get("business_id", user["_id"])
        
        filter_dict = {"user_id": user_id}
        if status:
            filter_dict["status"] = status
        
        from server import db
        renders = await db.shotstack_renders.find(filter_dict).sort("created_at", -1).limit(limit).to_list(None)
        
        # Remove sensitive data
        for render in renders:
            render.pop("timeline", None)
            render.pop("shotstack_response", None)
        
        return {"renders": renders}
    
    @router.delete("/render/{render_id}", response_model=Dict[str, Any])
    async def delete_render(render_id: str, user=Depends(user_dep)):
        """Delete a render job (local record only)."""
        user_id = user.get("business_id", user["_id"])
        
        from server import db
        result = await db.shotstack_renders.delete_one({"_id": render_id, "user_id": user_id})
        if result.deleted_count == 0:
            raise HTTPException(404, "Render job not found")
        
        return {"status": "deleted", "id": render_id}
    
    # ── Utility Endpoints ─────────────────────────────────────────────────────
    
    @router.get("/voices", response_model=Dict[str, Any])
    async def list_voices():
        """List available TTS voices."""
        # Standard Shotstack voices
        voices = {
            "english": [
                {"id": "samantha", "name": "Samantha", "language": "en-US", "gender": "female"},
                {"id": "matthew", "name": "Matthew", "language": "en-US", "gender": "male"},
                {"id": "joanna", "name": "Joanna", "language": "en-US", "gender": "female"},
                {"id": "joseph", "name": "Joseph", "language": "en-US", "gender": "male"},
                {"id": "lisa", "name": "Lisa", "language": "en-GB", "gender": "female"},
                {"id": "brian", "name": "Brian", "language": "en-GB", "gender": "male"},
            ],
            "other": [
                {"id": "camila", "name": "Camila", "language": "es-ES", "gender": "female"},
                {"id": "penelope", "name": "Penelope", "language": "es-US", "gender": "female"},
                {"id": "chantal", "name": "Chantal", "language": "fr-FR", "gender": "female"},
                {"id": "hans", "name": "Hans", "language": "de-DE", "gender": "male"},
                {"id": "zoe", "name": "Zoe", "language": "it-IT", "gender": "female"},
            ]
        }
        return {"voices": voices}
    
    @router.get("/stock", response_model=Dict[str, Any])
    async def search_stock_media(query: str = "", type: str = "video", limit: int = 20):
        """Search stock media (placeholder - integrate with Shotstack stock API)."""
        # This would integrate with Shotstack's stock media search
        return {
            "query": query,
            "type": type,
            "results": [],
            "message": "Stock media search not implemented - use Shotstack stock assets directly"
        }
    
    return router
