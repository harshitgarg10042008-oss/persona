import os

filepath = r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona\AnalysisModules\AnalysisAPI\views.py"

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find where resume_reviewer_upload starts
upload_idx = -1
for i, line in enumerate(lines):
    if "def resume_reviewer_upload(request):" in line:
        # Actually we know it's fine until resume_reviewer_result
        pass
    if "def resume_reviewer_result(request, review_id):" in line:
        # It got mangled here
        pass

# The mangling started deleting resume_reviewer_upload around line 3210.
# Let's find "review.save()" and "return redirect('analysis:resume_reviewer_result', review_id=review.id)"
restore_point = -1
for i, line in enumerate(lines):
    if "return redirect('analysis:resume_reviewer_result', review_id=review.id)" in line:
        restore_point = i
        break

if restore_point != -1:
    good_lines = lines[:restore_point + 1]
    
    rest_of_file = """        
    return render(request, 'analysis/resume_reviewer_upload.html')

@login_required
def resume_reviewer_result(request, review_id):
    from django.http import Http404
    review = get_object_or_404(ResumeReview, id=review_id)
    if review.user != request.user:
        raise Http404("Not found")

    total_reviews = ResumeReview.objects.filter(user=request.user).count()
    return render(request, 'analysis/resume_reviewer_result.html', {
        'review': review,
        'total_reviews': total_reviews,
    })

@login_required
def resume_reviewer_history(request):
    # Fetch all reviews ordered newest-first for display
    reviews_qs = list(
        ResumeReview.objects.filter(user=request.user).order_by('-version_number')
    )

    # Build a version_number → overall_score lookup for delta computation
    score_by_version = {r.version_number: r.overall_score for r in reviews_qs}

    # Annotate each review with its score delta vs the previous version
    annotated = []
    for review in reviews_qs:
        prev_score = score_by_version.get(review.version_number - 1)
        if prev_score is not None:
            delta = round(review.overall_score - prev_score, 2)
        else:
            delta = None  # first version — no comparison
        annotated.append({'review': review, 'delta': delta})

    return render(request, 'analysis/resume_reviewer_history.html', {
        'annotated_reviews': annotated,
    })


# =====================================
# COVER LETTER GENERATOR VIEWS
# =====================================
from .models import CoverLetter

@login_required
def cover_letter_generate(request):
    if request.method == 'POST':
        job_title = request.POST.get('job_title')
        company_name = request.POST.get('company_name', '')
        job_description = request.POST.get('job_description', '')
        resume_review_id = request.POST.get('resume_review_id')

        if not job_title:
            messages.error(request, 'Job title is required.')
            return redirect('analysis:cover_letter_generate')

        resume_context = ""
        resume_review = None
        if resume_review_id:
            try:
                resume_review = ResumeReview.objects.get(id=resume_review_id, user=request.user)
                resume_context = _extract_resume_text(resume_review.resume_file)
            except ResumeReview.DoesNotExist:
                messages.error(request, 'Selected resume review not found.')
                return redirect('analysis:cover_letter_generate')
            except Exception as e:
                messages.error(request, f'Failed to extract resume text: {str(e)}')
                return redirect('analysis:cover_letter_generate')

        prompt = (
            "You are an expert career coach and professional copywriter. "
            "Write a compelling, professional cover letter for the following job.\\n\\n"
            f"Job Title: {job_title}\\n"
        )
        if company_name:
            prompt += f"Company Name: {company_name}\\n"
        if job_description:
            prompt += f"Job Description:\\n{job_description}\\n"
        if resume_context:
            prompt += f"\\nApplicant's Resume Context:\\n{resume_context}\\n"
        
        prompt += (
            "\\nOutput ONLY the cover letter text. Do not include markdown formatting like ``` or introductory/concluding remarks."
        )

        try:
            generated_text = _call_groq(prompt, timeout=45)
            if not generated_text:
                raise ValueError("Empty response from Groq")
            
            # Clean up potential markdown formatting
            generated_text = generated_text.strip()
            if generated_text.startswith('```'):
                lines = generated_text.split('\\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                generated_text = '\\n'.join(lines).strip()

            cover_letter = CoverLetter.objects.create(
                user=request.user,
                job_title=job_title,
                company_name=company_name,
                job_description=job_description,
                resume_review=resume_review,
                generated_text=generated_text
            )
            return redirect('analysis:cover_letter_result', letter_id=cover_letter.id)
            
        except Exception as e:
            messages.error(request, 'Failed to generate cover letter. Please try again.')
            return redirect('analysis:cover_letter_generate')

    # GET request
    resume_reviews = ResumeReview.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/cover_letter_generate.html', {
        'resume_reviews': resume_reviews
    })

@login_required
def cover_letter_result(request, letter_id):
    from django.http import Http404
    cover_letter = get_object_or_404(CoverLetter, id=letter_id)
    if cover_letter.user != request.user:
        raise Http404("Not found")

    return render(request, 'analysis/cover_letter_result.html', {
        'cover_letter': cover_letter,
    })

@login_required
def cover_letter_history(request):
    cover_letters = CoverLetter.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/cover_letter_history.html', {
        'cover_letters': cover_letters,
    })


# =====================================
# LINKEDIN POST GENERATOR VIEWS
# =====================================
from .models import LinkedInPost

@login_required
def linkedin_post_generate(request):
    if request.method == 'POST':
        topic = request.POST.get('topic')
        tone = request.POST.get('tone', 'professional')
        resume_review_id = request.POST.get('resume_review_id')

        if not topic:
            messages.error(request, 'Topic is required.')
            return redirect('analysis:linkedin_post_generate')

        resume_context = ""
        resume_review = None
        if resume_review_id:
            try:
                resume_review = ResumeReview.objects.get(id=resume_review_id, user=request.user)
                resume_context = _extract_resume_text(resume_review.resume_file)
            except ResumeReview.DoesNotExist:
                messages.error(request, 'Selected resume review not found.')
                return redirect('analysis:linkedin_post_generate')
            except Exception as e:
                messages.error(request, f'Failed to extract resume text: {str(e)}')
                return redirect('analysis:linkedin_post_generate')

        prompt = (
            "You are an expert personal branding consultant and social media manager. "
            f"Write an engaging LinkedIn post about the following topic: {topic}\\n"
            f"The tone of the post should be: {tone}.\\n"
        )
        if resume_context:
            prompt += f"\\nUse the following resume context to make the post highly personalized and relevant to the author's background:\\n{resume_context}\\n"
        
        prompt += (
            "\\nOutput ONLY the text of the LinkedIn post. Do not include any introductory remarks, "
            "concluding remarks, or markdown code block formatting (like ```). Include relevant emojis and hashtags."
        )

        try:
            generated_text = _call_groq(prompt, timeout=45)
            if not generated_text:
                raise ValueError("Empty response from Groq")
            
            # Clean up potential markdown formatting
            generated_text = generated_text.strip()
            if generated_text.startswith('```'):
                lines = generated_text.split('\\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                generated_text = '\\n'.join(lines).strip()

            linkedin_post = LinkedInPost.objects.create(
                user=request.user,
                topic=topic,
                tone=tone,
                resume_review=resume_review,
                generated_text=generated_text
            )
            return redirect('analysis:linkedin_post_result', post_id=linkedin_post.id)
            
        except Exception as e:
            messages.error(request, 'Failed to generate LinkedIn post. Please try again.')
            return redirect('analysis:linkedin_post_generate')

    # GET request
    resume_reviews = ResumeReview.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/linkedin_post_generate.html', {
        'resume_reviews': resume_reviews
    })

@login_required
def linkedin_post_result(request, post_id):
    from django.http import Http404
    post = get_object_or_404(LinkedInPost, id=post_id)
    if post.user != request.user:
        raise Http404("Not found")

    return render(request, 'analysis/linkedin_post_result.html', {
        'post': post,
    })

@login_required
def linkedin_post_history(request):
    posts = LinkedInPost.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/linkedin_post_history.html', {
        'posts': posts,
    })
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(good_lines)
        f.write(rest_of_file)
    print("Fixed views.py")
else:
    print("Could not find restore point")
