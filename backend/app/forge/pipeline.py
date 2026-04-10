import random
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.forge_session import ForgeSession
from app.models.resident import Resident
from app.forge.router_stage import InputRouter
from app.forge.research_stage import ResearchStage
from app.forge.extraction_stage import ExtractionStage
from app.forge.build_stage import BuildStage
from app.forge.validation_stage import ValidationStage
from app.forge.refinement_stage import RefinementStage
from app.config import settings


class ForgePipeline:
    def __init__(
        self,
        db: AsyncSession,
        system_client,
        user_client,
        model: str | None = None,
        searxng_url: str | None = None,
    ):
        self._db = db
        self._system_client = system_client
        self._user_client = user_client
        self._model = model or settings.effective_model
        self._searxng_url = searxng_url or f"{settings.searxng_url}/search"

    async def start(
        self,
        user_id: str,
        character_name: str,
        raw_text: str = "",
        user_material: str = "",
    ) -> ForgeSession:
        """Start a new forge session. Routes to quick or deep mode."""
        router = InputRouter(llm_client=self._system_client, model=self._model)
        route_result = await router.run(character_name, raw_text, user_material)

        session = ForgeSession(
            user_id=user_id,
            character_name=character_name,
            mode=route_result["mode"],
            status="routing",
            current_stage="router",
            research_data={},
            extraction_data={},
            build_output={},
            validation_report={},
            refinement_log={},
        )
        # Store raw inputs in research_data for later use
        session.research_data = {
            "raw_text": raw_text,
            "user_material": user_material,
            "route_result": route_result,
        }
        session.status = "routed"

        self._db.add(session)
        await self._db.commit()
        await self._db.refresh(session)
        return session

    async def run_to_completion(self, session_id: str) -> ForgeSession:
        """Run the pipeline to completion based on session mode."""
        result = await self._db.execute(
            select(ForgeSession).where(ForgeSession.id == session_id)
        )
        session = result.scalar_one()

        try:
            if session.mode == "deep":
                await self._run_deep(session)
            else:
                await self._run_quick(session)

            # Create Resident from completed session
            await self._create_resident(session)
            session.status = "done"
        except Exception as e:
            session.status = "error"
            session.refinement_log = {
                **(session.refinement_log or {}),
                "error": str(e),
            }

        await self._db.commit()
        return session

    async def _create_resident(self, session: ForgeSession):
        """Create a Resident from a completed forge session."""
        from app.services.forge_service import DISTRICT_TILE_SLOTS, SPRITE_KEYS
        from app.services.coin_service import reward
        from app.services.scoring_service import compute_star_rating

        build = session.build_output or {}
        ability_md = build.get("ability_md", "")
        persona_md = build.get("persona_md", "")
        soul_md = build.get("soul_md", "")
        name = session.character_name

        # Generate slug
        slug = name.lower().strip()
        slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-') or f"resident-{session.id[:8]}"

        # Determine district from ability text
        district = "free"
        text = (ability_md + persona_md).lower()
        if any(k in text for k in ("工程", "代码", "编程", "engineer", "code", "dev")):
            district = "engineering"
        elif any(k in text for k in ("产品", "设计", "product", "design", "创业")):
            district = "product"
        elif any(k in text for k in ("学术", "研究", "教育", "academy", "research", "教授")):
            district = "academy"

        # Find available tile
        slots = DISTRICT_TILE_SLOTS.get(district, DISTRICT_TILE_SLOTS["free"])
        result = await self._db.execute(
            select(Resident.tile_x, Resident.tile_y).where(Resident.district == district)
        )
        occupied = {(r.tile_x, r.tile_y) for r in result.all()}
        tile_x, tile_y = slots[0]
        for x, y in slots:
            if (x, y) not in occupied:
                tile_x, tile_y = x, y
                break

        resident = Resident(
            slug=slug, name=name, district=district, status="idle", heat=10,
            model_tier="standard", token_cost_per_turn=1, creator_id=session.user_id,
            ability_md=ability_md, persona_md=persona_md, soul_md=soul_md,
            meta_json={"origin": "forge"},
            sprite_key=random.choice(SPRITE_KEYS),
            tile_x=tile_x, tile_y=tile_y, star_rating=2,
        )
        self._db.add(resident)
        await self._db.flush()

        # Reward creator
        await reward(self._db, session.user_id, 50, "forge_creation")

    async def _run_quick(self, session: ForgeSession):
        """Quick mode: BuildStage only."""
        session.status = "building"
        session.current_stage = "build"
        await self._db.commit()

        raw_text = session.research_data.get("raw_text", "")
        user_material = session.research_data.get("user_material", "")
        input_text = user_material or raw_text or session.character_name

        build = BuildStage(llm_client=self._user_client, model=self._model)
        build_result = await build.run(
            character_name=session.character_name,
            research_text=input_text,
        )
        session.build_output = build_result
        # Clear research_data to signal research was skipped
        session.research_data = {}

    async def _run_deep(self, session: ForgeSession):
        """Deep mode: Research -> Extract -> Build -> Validate -> Refine."""
        user_material = session.research_data.get("user_material", "")

        # Stage 1: Research
        session.status = "researching"
        session.current_stage = "research"
        await self._db.commit()

        research = ResearchStage(searxng_url=self._searxng_url)
        research_results = await research.run(session.character_name, user_material)
        research_text = research.format_for_llm(research_results, user_material)
        session.research_data = {
            **session.research_data,
            "search_results": {k: len(v) for k, v in research_results.items()},
            "research_text_length": len(research_text),
        }
        await self._db.commit()

        # Stage 2: Extraction
        session.status = "extracting"
        session.current_stage = "extraction"
        await self._db.commit()

        extraction = ExtractionStage(llm_client=self._user_client, model=self._model)
        extraction_result = await extraction.run(research_text, session.character_name)
        session.extraction_data = extraction_result
        await self._db.commit()

        # Stage 3: Build
        session.status = "building"
        session.current_stage = "build"
        await self._db.commit()

        build = BuildStage(llm_client=self._user_client, model=self._model)
        build_result = await build.run(
            character_name=session.character_name,
            research_text=research_text,
            extraction_data=extraction_result,
        )
        session.build_output = build_result
        await self._db.commit()

        # Stage 4: Validation
        session.status = "validating"
        session.current_stage = "validation"
        await self._db.commit()

        validation = ValidationStage(llm_client=self._user_client, model=self._model)
        validation_report = await validation.run(
            character_name=session.character_name,
            ability_md=build_result["ability_md"],
            persona_md=build_result["persona_md"],
            soul_md=build_result["soul_md"],
        )
        session.validation_report = validation_report
        await self._db.commit()

        # Stage 5: Refinement
        session.status = "refining"
        session.current_stage = "refinement"
        await self._db.commit()

        refinement = RefinementStage(llm_client=self._user_client, model=self._model)
        refined = await refinement.run(
            character_name=session.character_name,
            ability_md=build_result["ability_md"],
            persona_md=build_result["persona_md"],
            soul_md=build_result["soul_md"],
            validation_report=validation_report,
        )
        session.build_output = {
            "ability_md": refined["ability_md"],
            "persona_md": refined["persona_md"],
            "soul_md": refined["soul_md"],
        }
        session.refinement_log = {"stages": refined.get("refinement_log", [])}
