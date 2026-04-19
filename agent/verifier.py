from __future__ import annotations

from agent.schemas import VerificationResult

class Verifier:
    def verify(self, answer: str, retrieved_items: list[dict]) -> VerificationResult:
        issues: list[str] =[]

        grounded = True
        if retrieved_items and "[" not in answer:
            grounded = False
            issues.append("Retrieved Answer has no citation markers.")
        
        if not answer.strip():
            grounded = False
            issues.append("Answer is empty.")

        status = "verified" 
        if issues:
            status = "needs_more_info"

        return VerificationResult(
            status=status,
            issues=issues,
            grounded=grounded,
        )