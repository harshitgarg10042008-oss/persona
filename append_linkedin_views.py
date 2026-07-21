import os

views_path = os.path.join("AnalysisModules", "AnalysisAPI", "views.py")

linkedin_views = """

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

with open(views_path, 'a', encoding='utf-8') as f:
    f.write(linkedin_views)

print("Successfully appended LinkedIn Post views to views.py!")
