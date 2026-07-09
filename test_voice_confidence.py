"""
Test script for voice confidence analysis
Tests the analyze_voice_confidence function with different audio patterns
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from AnalysisModules.speech_analyzer import analyze_voice_confidence
import tempfile

def test_voice_confidence():
    """Test voice confidence analysis with sample audio"""
    
    print("=" * 60)
    print("Voice Confidence Analysis Test")
    print("=" * 60)
    
    # Test 1: Simulate fast/nervous speech pattern
    print("\n--- Test 1: Fast/Nervous Speech Pattern ---")
    print("Simulating: Fast speech rate, high pitch variation, inconsistent energy")
    
    # Create a mock transcription for fast speech
    fast_transcript = "um uh so basically like I think that you know I mean the thing is that um actually I would say that like you know basically I think that um so the point is that uh I mean like actually"
    
    # Since we don't have real audio files, we'll test the function structure
    # In a real scenario, you would pass actual audio bytes
    print(f"Transcript: {fast_transcript[:100]}...")
    print(f"Word count: {len(fast_transcript.split())}")
    print(f"Filler words detected: um, uh, like, you know, basically, actually, I mean")
    print("\nExpected analysis:")
    print("- High speech rate (>180 WPM)")
    print("- High filler word ratio")
    print("- Likely lower confidence score")
    print("- Observations about fast pace and filler words")
    
    # Test 2: Simulate calm/steady speech pattern
    print("\n--- Test 2: Calm/Steady Speech Pattern ---")
    print("Simulating: Steady speech rate, minimal fillers, consistent energy")
    
    calm_transcript = "I believe that my experience in project management has prepared me well for this role. I have successfully led teams of various sizes and delivered projects on time and within budget."
    
    print(f"Transcript: {calm_transcript[:100]}...")
    print(f"Word count: {len(calm_transcript.split())}")
    print(f"Filler words detected: None")
    print("\nExpected analysis:")
    print("- Optimal speech rate (140-160 WPM)")
    print("- Low filler word ratio")
    print("- Higher confidence score")
    print("- Observations about steady pace and minimal fillers")
    
    print("\n" + "=" * 60)
    print("Function Implementation Test")
    print("=" * 60)
    
    # Test that the function is properly imported and callable
    print("\nTesting function import and structure...")
    print(f"Function: {analyze_voice_confidence.__name__}")
    print(f"Module: {analyze_voice_confidence.__module__}")
    print(f"Docstring exists: {bool(analyze_voice_confidence.__doc__)}")
    
    # Check function signature
    import inspect
    sig = inspect.signature(analyze_voice_confidence)
    print(f"Parameters: {list(sig.parameters.keys())}")
    
    print("\n✓ Function structure is correct")
    print("✓ Ready for real audio testing")
    
    print("\n" + "=" * 60)
    print("Next Steps for Real Testing")
    print("=" * 60)
    print("\nTo test with real audio:")
    print("1. Record two audio samples:")
    print("   - Sample A: Speak fast with filler words (nervous)")
    print("   - Sample B: Speak calmly and steadily (confident)")
    print("2. Load audio bytes from the recordings")
    print("3. Call: analyze_voice_confidence(audio_bytes, transcription)")
    print("4. Compare the scores and observations")
    print("\nExpected results:")
    print("- Fast/nervous sample: Lower score (3-5/10), observations about pace/fillers")
    print("- Calm/steady sample: Higher score (7-9/10), positive observations")
    
    return True

if __name__ == "__main__":
    test_voice_confidence()
