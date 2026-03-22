"""Services package."""

from app.services.attachment_normalization import AttachmentNormalizationService
from app.services.eligibility import ScholarshipEligibilityService
from app.services.notice_collection import NoticeCollectionService
from app.services.notice_normalization import NoticeHtmlNormalizationService
from app.services.rule_extraction import ScholarshipRuleExtractionService
from app.services.search import ScholarshipSearchService

__all__ = [
    "AttachmentNormalizationService",
    "ScholarshipEligibilityService",
    "NoticeCollectionService",
    "NoticeHtmlNormalizationService",
    "ScholarshipRuleExtractionService",
    "ScholarshipSearchService",
]
