"""
Chronicling America (Library of Congress) Harvester.
Fetches pre-1930 newspaper pages, extracts OCR text, structures them into Seed Cards,
and stores them in the database.
"""

import time
import json
import uuid
import requests
from typing import Dict, Any, List, Optional
from utils.config import CONFIG, GEMINI_API_KEY
from db.database import save_seed, get_seed_stock_counts

LOC_SEARCH_URL = "https://www.loc.gov/collections/chronicling-america/"

class LocHarvester:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.rate_limit_delay = CONFIG.get("harvest", {}).get("rate_limit_delay_seconds", 2.5)
        self.max_year = CONFIG.get("harvest", {}).get("max_year", 1930)
        self.headers = {
            "User-Agent": "ArchiveMicroStoryBot/1.0 (Educational Historical Research; mailto:contact@example.com)"
        }

    def fetch_pages_for_keyword(self, query: str, rows: int = 5) -> List[Dict[str, Any]]:
        """Queries loc.gov for newspaper pages matching the keyword before 1930."""
        params = {
            "fo": "json",
            "q": query,
            "dates": f"1850/{self.max_year}",
            "c": rows,
            "sp": 1
        }
        
        try:
            resp = requests.get(LOC_SEARCH_URL, params=params, headers=self.headers, timeout=15)
            time.sleep(self.rate_limit_delay)
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])
            else:
                print(f"[Harvester] loc.gov returned status {resp.status_code}")
                return []
        except Exception as e:
            print(f"[Harvester] Network error querying loc.gov: {e}")
            return []

    def extract_seed_with_gemini(self, ocr_text: str, default_format: str, default_pillar: str) -> Optional[Dict[str, Any]]:
        """Uses Gemini to parse messy OCR text into a structured seed card."""
        if not self.api_key:
            return None
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=self.api_key)
            prompt_path = "prompts/seed_extraction.md"
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
                
            prompt = template.replace("{{ocr_text}}", ocr_text[:4000])
            
            response = client.models.generate_content(
                model=CONFIG["models"]["draft"],
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            
            parsed = json.loads(response.text)
            if parsed.get("usable"):
                parsed["format"] = parsed.get("format") or default_format
                parsed["pillar"] = parsed.get("pillar") or default_pillar
                return parsed
        except Exception as e:
            print(f"[Harvester] Gemini extraction error: {e}")
            
        return None

    def harvest_all_formats(self, seeds_per_format: int = 2) -> Dict[str, int]:
        """Harvests seeds across all formats according to config keywords."""
        stock = get_seed_stock_counts()
        print(f"[Harvester] Current seed stock: {stock}")
        
        added_counts = {fmt: 0 for fmt in CONFIG["formats"]}
        
        for fmt, f_cfg in CONFIG["formats"].items():
            keywords = f_cfg.get("keywords", ["historic"])
            for kw in keywords[:2]:
                if added_counts[fmt] >= seeds_per_format:
                    break
                print(f"[Harvester] Searching loc.gov for '{kw}' (Format: {fmt})...")
                results = self.fetch_pages_for_keyword(kw, rows=3)
                
                for item in results:
                    # Extract OCR text and images
                    ocr_text = ""
                    if "description" in item:
                        ocr_text = " ".join(item["description"])
                    
                    if len(ocr_text.strip()) < 80:
                        continue
                        
                    # Structure with Gemini
                    seed_data = self.extract_seed_with_gemini(
                        ocr_text=ocr_text,
                        default_format=fmt,
                        default_pillar="money"
                    )
                    
                    if seed_data and seed_data.get("usable"):
                        seed_id = f"ca-{uuid.uuid4().hex[:8]}"
                        seed_data["seed_id"] = seed_id
                        seed_data["source"] = "Chronicling America"
                        seed_data["source_url"] = item.get("id", "")
                        seed_data["ocr_text"] = ocr_text
                        seed_data["page_image_url"] = item.get("image_url", [""])[0] if item.get("image_url") else ""
                        
                        saved = save_seed(seed_data)
                        if saved:
                            added_counts[fmt] += 1
                            print(f"[Harvester] Saved seed {seed_id} for {fmt}")
                            
        return added_counts

    def import_curated_seeds_file(self, file_path: str) -> int:
        """Loads vetted, pre-formatted seed cards from a JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            seeds = json.load(f)
            
        count = 0
        for s in seeds:
            if "seed_id" not in s:
                s["seed_id"] = f"curated-{uuid.uuid4().hex[:8]}"
            if save_seed(s):
                count += 1
        print(f"[Harvester] Imported {count} seeds from {file_path}")
        return count
