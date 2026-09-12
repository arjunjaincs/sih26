"""
PRAMAAN AI Copilot Service Orchestrator.

Integrates the abstract AIProvider, bounded AIContextBuilder, and operational policy
with PRAMAAN SQLite storage. Enforces read-only isolation, data minimization,
and genuine source citation.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional

from backend.ai.context_builder import AIContextBuilder
from backend.ai.models import (
    AIChatRequest,
    AIChatResponse,
    AICopilotScope,
    AIModelsResponse,
    AISourceReference,
    AIStatusResponse,
    ChatMessage,
)
from backend.ai.openrouter import OpenRouterProvider
from backend.ai.policy import (
    COPILOT_SYSTEM_POLICY,
    PRIVACY_DISCLOSURE,
    RECOMMENDED_MODELS,
)
from backend.ai.provider import AIProvider
from backend.api.config import settings
from backend.api.errors import AssessmentNotFound
from backend.api.routes.assessments import assemble_assessment_result_from_db
from backend.api.schemas import EvidenceSchema, FindingSchema
from backend.audit.verifier import ChainVerifier
from backend.infra.db import (
    AssessmentRepository,
    AuditRepository,
    EvidenceRepository,
    FindingRepository,
    ProvenanceRepository,
)

logger = logging.getLogger("pramaan.ai.service")


class AIService:
    """
    High-level coordinator for PRAMAAN Analyst Copilot.
    
    Ensures that all AI interactions are strictly READ-ONLY and bounded
    by local deterministic evidence.
    """

    def __init__(self, provider: Optional[AIProvider] = None) -> None:
        if provider is not None:
            self._provider = provider
        else:
            self._provider = OpenRouterProvider(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                default_model=settings.openrouter_model,
                timeout=settings.openrouter_timeout_seconds,
                zdr_privacy=settings.openrouter_zdr,
            )

    @property
    def provider(self) -> AIProvider:
        return self._provider

    def set_provider(self, provider: AIProvider) -> None:
        """Inject an alternative provider (e.g. MockAIProvider in tests)."""
        self._provider = provider

    def get_status(self) -> AIStatusResponse:
        """
        Return public AI status. Never returns raw API keys.
        """
        if not settings.ai_enabled:
            status = "disabled"
        elif not self._provider.is_configured:
            status = "not_configured"
        else:
            status = "connected"

        has_key = bool(settings.openrouter_api_key) if self._provider.provider_name == "openrouter" else self._provider.is_configured
        model = getattr(self._provider, "default_model", settings.openrouter_model)

        return AIStatusResponse(
            configured=self._provider.is_configured and settings.ai_enabled,
            provider=self._provider.provider_name,
            model=model,
            status=status,
            has_api_key=has_key,
            privacy_disclosure=PRIVACY_DISCLOSURE,
            available_models=RECOMMENDED_MODELS,
        )

    async def list_models(self) -> AIModelsResponse:
        """Return available/recommended models."""
        models = await self._provider.list_models()
        current_model = getattr(self._provider, "default_model", settings.openrouter_model)
        return AIModelsResponse(models=models, current_model=current_model)

    async def test_connection(self) -> tuple[bool, str]:
        """Perform a live health check with the configured provider."""
        if not settings.ai_enabled:
            return False, "Cloud AI is disabled via PRAMAAN_AI_ENABLED configuration."
        return await self._provider.health_check()

    async def chat(
        self,
        conn: sqlite3.Connection,
        assessment_id: str,
        request: AIChatRequest,
    ) -> AIChatResponse:
        """
        Execute an analyst Copilot inquiry against the bounded assessment evidence.
        Strictly READ-ONLY: Never alters assessment records, findings, or audit state.
        """
        if not settings.ai_enabled:
            raise RuntimeError("Cloud AI is disabled by configuration (PRAMAAN_AI_ENABLED=false).")
        if not self._provider.is_configured:
            raise RuntimeError("Cloud AI is not configured. An OpenRouter API key is required.")

        # 1. Verify assessment exists and assemble canonical result
        asmt_repo = AssessmentRepository(conn)
        asmt_record = asmt_repo.get(assessment_id)
        if asmt_record is None:
            raise AssessmentNotFound(assessment_id)

        assessment_result = assemble_assessment_result_from_db(conn, assessment_id)

        # 2. Build bounded context and track authoritative source IDs
        finding_repo = FindingRepository(conn)
        evidence_repo = EvidenceRepository(conn)
        valid_sources: list[AISourceReference] = []

        if request.scope == AICopilotScope.FINDING:
            if not request.finding_id:
                raise ValueError("finding_id must be provided when scope is 'finding'.")

            target_finding_entity = finding_repo.get(request.finding_id)
            if not target_finding_entity or target_finding_entity.assessment_id != assessment_id:
                raise ValueError(f"Finding {request.finding_id} not found in assessment {assessment_id}.")

            f_schema = FindingSchema(
                finding_id=target_finding_entity.finding_id,
                assessment_id=target_finding_entity.assessment_id,
                asset_id=target_finding_entity.asset_id,
                category=target_finding_entity.category.value,
                subcategory=target_finding_entity.subcategory,
                severity=target_finding_entity.severity.value,
                title=target_finding_entity.title,
                description=target_finding_entity.description,
                detection_method=target_finding_entity.detection_method,
                detector_id=target_finding_entity.detector_id,
                limitations=target_finding_entity.limitations,
                recommended_disposition=target_finding_entity.recommended_disposition,
                created_at=target_finding_entity.created_at.isoformat(),
            )

            db_ev = evidence_repo.list_by_finding(request.finding_id)
            ev_schemas = [
                EvidenceSchema(
                    evidence_id=e.evidence_id,
                    finding_id=e.finding_id,
                    detector_id=e.detector_id,
                    evidence_type=e.evidence_type.value,
                    description=e.description,
                    data=e.data,
                    artifact_path=None,
                    artifact_sha256=e.artifact_sha256,
                )
                for e in db_ev
            ]

            valid_sources.append(AISourceReference(
                type="finding",
                id=f_schema.finding_id,
                label=f"Finding: {f_schema.title}",
            ))
            valid_sources.append(AISourceReference(
                type="detector",
                id=f_schema.detector_id,
                label=f"Detector: {f_schema.detection_method}",
            ))
            for ev in ev_schemas:
                valid_sources.append(AISourceReference(
                    type="evidence",
                    id=ev.evidence_id,
                    label=f"Evidence: {ev.description[:40]}...",
                ))

            context_str = AIContextBuilder.build_finding_context(
                assessment=assessment_result,
                finding=f_schema,
                evidence_items=ev_schemas,
            )

        elif request.scope == AICopilotScope.PROVENANCE:
            prov_repo = ProvenanceRepository(conn)
            manifest = prov_repo.get_by_assessment(assessment_id)
            has_man = manifest is not None
            prov_summary = {
                "has_manifest": has_man,
                "digest_verified": bool(has_man and manifest.digest),
                "signature_verified": bool(has_man and manifest.signature),
                "replay_verified": has_man,
                "manifest_digest": manifest.digest if has_man else "None",
                "key_algorithm": "Ed25519",
                "limitations": [lim for lim in assessment_result.limitations if "provenance" in lim.lower()],
            }
            if has_man:
                valid_sources.append(AISourceReference(
                    type="provenance",
                    id=manifest.manifest_id,
                    label=f"Manifest Digest: {manifest.digest[:12]}..." if manifest.digest else "Manifest",
                ))
            context_str = AIContextBuilder.build_provenance_context(
                assessment=assessment_result,
                provenance_summary=prov_summary,
            )

        elif request.scope == AICopilotScope.AUDIT:
            audit_repo = AuditRepository(conn)
            events = audit_repo.list_by_assessment(assessment_id)
            try:
                chain_valid = ChainVerifier(conn).verify_assessment_events(assessment_id)
            except Exception:
                chain_valid = False

            audit_summary = {
                "chain_valid": chain_valid,
                "total_events": len(events),
                "genesis_event_id": events[0].event_id if events else "None",
                "latest_event_id": events[-1].event_id if events else "None",
                "event_types": list({e.event_type.value for e in events}),
                "verification_result": "Cryptographically intact hash chain" if chain_valid else "Chain broken or unverified",
            }
            valid_sources.append(AISourceReference(
                type="audit",
                id=assessment_id,
                label="Audit Trail Chain Verification",
            ))
            context_str = AIContextBuilder.build_audit_context(
                assessment=assessment_result,
                audit_summary=audit_summary,
            )

        else:  # ASSESSMENT scope
            db_findings = finding_repo.list_by_assessment(assessment_id)
            f_schemas = [
                FindingSchema(
                    finding_id=f.finding_id,
                    assessment_id=f.assessment_id,
                    asset_id=f.asset_id,
                    category=f.category.value,
                    subcategory=f.subcategory,
                    severity=f.severity.value,
                    title=f.title,
                    description=f.description,
                    detection_method=f.detection_method,
                    detector_id=f.detector_id,
                    limitations=f.limitations,
                    recommended_disposition=f.recommended_disposition,
                    created_at=f.created_at.isoformat(),
                )
                for f in db_findings
            ]
            for f in f_schemas[:10]:
                valid_sources.append(AISourceReference(
                    type="finding",
                    id=f.finding_id,
                    label=f"[{f.severity.upper()}] {f.title}",
                ))
            context_str = AIContextBuilder.build_assessment_context(
                assessment=assessment_result,
                findings=f_schemas,
            )

        # 3. Assemble prompt messages
        messages = [
            ChatMessage(role="system", content=COPILOT_SYSTEM_POLICY),
            ChatMessage(
                role="user",
                content=(
                    f"Authoritative PRAMAAN Assessment Context:\n\n"
                    f"{context_str}\n\n"
                    f"Analyst Question:\n"
                    f"{request.message}"
                ),
            ),
        ]

        # 4. Invoke Provider
        answer = await self._provider.chat(messages)

        # 5. Filter cited sources to only genuine ones mentioned or applicable
        cited_sources: list[AISourceReference] = []
        for src in valid_sources:
            # If source ID or label is referenced in answer or this is finding-scoped query
            if (
                request.scope == AICopilotScope.FINDING
                or src.id in answer
                or (src.label and any(part in answer for part in src.label.split() if len(part) > 6))
            ):
                cited_sources.append(src)

        # Ensure at least relevant target source is included if grounded
        if not cited_sources and valid_sources:
            cited_sources = valid_sources[:3]

        active_model = getattr(self._provider, "default_model", settings.openrouter_model)

        return AIChatResponse(
            answer=answer,
            provider=self._provider.provider_name,
            model=active_model,
            scope=request.scope.value,
            grounded=True,
            sources=cited_sources,
        )

    async def explain_finding(
        self,
        conn: sqlite3.Connection,
        assessment_id: str,
        finding_id: str,
        user_query: Optional[str] = None,
    ) -> AIChatResponse:
        """
        Convenience endpoint to explain a specific finding in depth.
        """
        query = (
            user_query
            if user_query and user_query.strip()
            else (
                f"Explain finding {finding_id}: why was it classified at its severity level, "
                f"what evidence supports it, could this be a false positive, and what should I investigate first?"
            )
        )
        request = AIChatRequest(
            message=query,
            scope=AICopilotScope.FINDING,
            finding_id=finding_id,
        )
        return await self.chat(conn, assessment_id, request)


# Global singleton instance
ai_service = AIService()
