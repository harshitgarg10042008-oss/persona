"""Backfill assessment scores from existing snapshot/response analysis_data."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment
from AnalysisAPI.views import _snapshot_score_from_data

assessment = IndividualAssessment.objects.order_by('-started_at').first()
print(f"Backfilling assessment {assessment.id} (status={assessment.status})")

snapshots = assessment.snapshots.all()
body_scores = []
attire_scores = []
for s in snapshots:
    score = _snapshot_score_from_data(s)
    if score is not None and score > 0:
        if s.analysis_type == 'body_language':
            body_scores.append(score)
        elif s.analysis_type == 'attire':
            attire_scores.append(score)
        if s.score is None:
            s.score = score
            s.save(update_fields=['score'])

if body_scores:
    assessment.body_language_score = sum(body_scores) / len(body_scores)
    print(f"body_language_score = {assessment.body_language_score:.2f} (from {len(body_scores)} snapshots)")
if attire_scores:
    assessment.attire_score = sum(attire_scores) / len(attire_scores)
    print(f"attire_score = {assessment.attire_score:.2f} (from {len(attire_scores)} snapshots)")

scores = [s for s in [assessment.speaking_score, assessment.body_language_score, assessment.attire_score] if s is not None]
if scores:
    assessment.overall_score = sum(scores) / len(scores)
    print(f"overall_score = {assessment.overall_score:.2f}")

assessment.save()
print("Done.")
