import cv2
import mediapipe as mp
import numpy as np
import time
import math

class BodyLanguageAnalyzer:
    def __init__(self):
        # setup mediapipe stuff
        self.mp_pose = mp.solutions.pose
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        
        # face tracking for eye contact
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        
        # tracking stuff
        self.feedback_history = {
            'posture': [],
            'eye_contact': [],
            'gestures': []
        }
        
        self.previous_hand_positions = {}
        self.hand_movement_history = []
        
    def calculate_angle(self, a, b, c):
        # get angle between three points
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)
        
        radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
        angle = np.abs(radians * 180.0 / np.pi)
        
        if angle > 180.0:
            angle = 360 - angle
            
        return angle
    
    def analyze_posture(self, landmarks):
        # check if person is sitting/standing properly
        try:
            # get important body points
            left_shoulder = [landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value].x,
                           landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
            right_shoulder = [landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x,
                            landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y]
            left_hip = [landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value].x,
                       landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value].y]
            right_hip = [landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value].x,
                        landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value].y]
            nose = [landmarks[self.mp_pose.PoseLandmark.NOSE.value].x,
                   landmarks[self.mp_pose.PoseLandmark.NOSE.value].y]
            left_ear = [landmarks[self.mp_pose.PoseLandmark.LEFT_EAR.value].x,
                       landmarks[self.mp_pose.PoseLandmark.LEFT_EAR.value].y]
            right_ear = [landmarks[self.mp_pose.PoseLandmark.RIGHT_EAR.value].x,
                        landmarks[self.mp_pose.PoseLandmark.RIGHT_EAR.value].y]
            
            # check how tilted shoulders are
            shoulder_slope = abs(left_shoulder[1] - right_shoulder[1])
            
            # spine center points
            spine_center_top = [(left_shoulder[0] + right_shoulder[0]) / 2,
                               (left_shoulder[1] + right_shoulder[1]) / 2]
            spine_center_bottom = [(left_hip[0] + right_hip[0]) / 2,
                                  (left_hip[1] + right_hip[1]) / 2]
            
            # check head position 
            head_side_alignment = abs(nose[0] - spine_center_top[0])
            
            # forward/backward lean detection using ears
            ear_center = [(left_ear[0] + right_ear[0]) / 2, (left_ear[1] + right_ear[1]) / 2]
            forward_lean = abs(ear_center[0] - spine_center_top[0])
            
            # slouching check
            vertical_alignment = abs(spine_center_top[1] - spine_center_bottom[1])
            
            posture_score = 100
            feedback = []
            
            # shoulder level check
            if shoulder_slope > 0.03:
                deduction = min(40, shoulder_slope * 800)
                posture_score -= deduction
                feedback.append("Level your shoulders!")
            
            # head tilting
            if head_side_alignment > 0.06:
                deduction = min(35, head_side_alignment * 500)
                posture_score -= deduction
                feedback.append("Center your head!")
            
            # leaning forward/back
            if forward_lean > 0.08:
                deduction = min(40, forward_lean * 400)
                posture_score -= deduction
                if ear_center[0] > spine_center_top[0]:
                    feedback.append("Stop leaning back!")
                else:
                    feedback.append("Stop leaning forward!")
            
            # slouching
            if vertical_alignment < 0.15:
                posture_score -= 25
                feedback.append("Sit up straight - don't slouch!")
            
            # spine angle check
            spine_angle = math.atan2(spine_center_bottom[1] - spine_center_top[1],
                                   spine_center_bottom[0] - spine_center_top[0]) * 180 / math.pi
            
            if abs(spine_angle - 90) > 10:
                deduction = min(30, abs(spine_angle - 90) * 2)
                posture_score -= deduction
                feedback.append("Straighten your spine!")
            
            posture_score = max(0, posture_score)
            
            # give feedback based on score
            if posture_score >= 90:
                feedback = ["Perfect posture!"]
            elif posture_score >= 80:
                feedback = ["Excellent posture!"]
            elif posture_score >= 70:
                feedback = ["Good posture, minor tweaks needed"]
            elif posture_score >= 50:
                if not feedback:
                    feedback = ["Fair posture, needs improvement"]
            else:
                if not feedback:
                    feedback = ["Poor posture - major adjustments needed"]
            
            return posture_score, feedback
            
        except Exception as e:
            return 0, ["Unable to analyze posture - no person detected"]
    
    def analyze_eye_contact(self, face_landmarks, image_shape):
        # check if person is looking at camera
        try:
            if not face_landmarks:
                return 0, ["No face detected"]
            
            # eye landmark points for mediapipe
            LEFT_EYE_INNER = 133
            LEFT_EYE_OUTER = 33
            RIGHT_EYE_INNER = 362
            RIGHT_EYE_OUTER = 263
            
            LEFT_PUPIL = 468
            RIGHT_PUPIL = 473
            
            h, w = image_shape[:2]
            
            # get eye positions
            left_eye_inner = face_landmarks.landmark[LEFT_EYE_INNER]
            left_eye_outer = face_landmarks.landmark[LEFT_EYE_OUTER]
            right_eye_inner = face_landmarks.landmark[RIGHT_EYE_INNER]
            right_eye_outer = face_landmarks.landmark[RIGHT_EYE_OUTER]
            
            # find eye centers
            left_eye_center_x = (left_eye_inner.x + left_eye_outer.x) / 2
            left_eye_center_y = (left_eye_inner.y + left_eye_outer.y) / 2
            right_eye_center_x = (right_eye_inner.x + right_eye_outer.x) / 2
            right_eye_center_y = (right_eye_inner.y + right_eye_outer.y) / 2
            
            eye_center_x = (left_eye_center_x + right_eye_center_x) / 2
            eye_center_y = (left_eye_center_y + right_eye_center_y) / 2
            
            # camera is at center
            center_x = 0.5
            center_y = 0.5
            
            # how far are eyes from camera center
            horizontal_deviation = abs(eye_center_x - center_x)
            vertical_deviation = abs(eye_center_y - center_y)
            
            total_deviation = math.sqrt(horizontal_deviation**2 + vertical_deviation**2)
            
            # convert to score
            max_deviation = 0.25
            eye_contact_score = max(0, 100 * (1 - (total_deviation / max_deviation)))
            
            eye_contact_score = min(100, eye_contact_score)
            
            feedback = []
            if eye_contact_score >= 90:
                feedback = ["Perfect eye contact!"]
            elif eye_contact_score >= 80:
                feedback = ["Excellent eye contact!"]
            elif eye_contact_score >= 70:
                feedback = ["Good eye contact"]
            elif eye_contact_score >= 50:
                feedback = ["Look more towards the camera"]
            elif eye_contact_score >= 30:
                feedback = ["Poor eye contact - look at camera!"]
            else:
                feedback = ["No eye contact - look directly at camera!"]
            
            return eye_contact_score, feedback
            
        except Exception as e:
            return 0, ["Unable to analyze eye contact - no face detected"]
    
    def analyze_gestures(self, hand_landmarks):
        # check hand movements and finger positions
        try:
            if not hand_landmarks:
                return 0, ["No hands detected"]
            
            gesture_score = 80  # start decent
            feedback = []
            
            current_positions = {}
            
            for idx, hand in enumerate(hand_landmarks):
                hand_id = f"hand_{idx}"
                
                # get finger points
                wrist = hand.landmark[self.mp_hands.HandLandmark.WRIST]
                thumb_tip = hand.landmark[self.mp_hands.HandLandmark.THUMB_TIP]
                thumb_ip = hand.landmark[self.mp_hands.HandLandmark.THUMB_IP]
                index_tip = hand.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]
                index_pip = hand.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_PIP]
                middle_tip = hand.landmark[self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
                middle_pip = hand.landmark[self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP]
                ring_tip = hand.landmark[self.mp_hands.HandLandmark.RING_FINGER_TIP]
                ring_pip = hand.landmark[self.mp_hands.HandLandmark.RING_FINGER_PIP]
                pinky_tip = hand.landmark[self.mp_hands.HandLandmark.PINKY_TIP]
                pinky_pip = hand.landmark[self.mp_hands.HandLandmark.PINKY_PIP]
                
                current_positions[hand_id] = (wrist.x, wrist.y)
                
                # check which fingers are up
                fingers_up = []
                
                # thumb is weird
                if thumb_tip.x > thumb_ip.x:
                    fingers_up.append(1)
                else:
                    fingers_up.append(0)
                
                # other fingers
                finger_tips = [index_tip, middle_tip, ring_tip, pinky_tip]
                finger_pips = [index_pip, middle_pip, ring_pip, pinky_pip]
                
                for tip, pip in zip(finger_tips, finger_pips):
                    if tip.y < pip.y:  # finger pointing up
                        fingers_up.append(1)
                    else:
                        fingers_up.append(0)
                
                total_fingers_up = sum(fingers_up)
                
                # judge finger positions
                if total_fingers_up == 0:  # fist
                    gesture_score += 5
                elif total_fingers_up == 5:  # open hand
                    gesture_score += 10
                elif total_fingers_up == 1:  # pointing
                    gesture_score -= 20
                    feedback.append("Avoid pointing gestures!")
                elif total_fingers_up == 2:
                    if fingers_up[1] == 1 and fingers_up[2] == 1:  # peace sign
                        gesture_score -= 15
                        feedback.append("Avoid pointing with multiple fingers!")
                    else:
                        gesture_score -= 5
                elif total_fingers_up == 3:
                    gesture_score -= 10
                    feedback.append("Avoid complex finger gestures!")
                elif total_fingers_up == 4:
                    gesture_score -= 5
                
                # check for bad gestures
                if fingers_up[2] == 1 and sum(fingers_up) == 1:  # middle finger
                    gesture_score -= 50
                    feedback.append("Inappropriate gesture detected!")
                
                # hand position check
                if wrist.y > 0.9:  # too low
                    gesture_score -= 10
                    feedback.append("Raise your hands slightly")
                elif wrist.y < 0.3:  # too high
                    gesture_score -= 10
                    feedback.append("Lower your hands slightly")
                else:
                    gesture_score += 5
            
            # check hand movement speed
            if len(current_positions) > 0:
                if hasattr(self, 'previous_hand_positions') and self.previous_hand_positions:
                    total_movement = 0
                    movement_count = 0
                    
                    for hand_id, (curr_x, curr_y) in current_positions.items():
                        if hand_id in self.previous_hand_positions:
                            prev_x, prev_y = self.previous_hand_positions[hand_id]
                            movement = math.sqrt((curr_x - prev_x)**2 + (curr_y - prev_y)**2)
                            total_movement += movement
                            movement_count += 1
                    
                    if movement_count > 0:
                        avg_movement = total_movement / movement_count
                        
                        self.hand_movement_history.append(avg_movement)
                        if len(self.hand_movement_history) > 10:
                            self.hand_movement_history.pop(0)
                        
                        if len(self.hand_movement_history) >= 5:
                            recent_avg_movement = sum(self.hand_movement_history) / len(self.hand_movement_history)
                            
                            if recent_avg_movement > 0.05:  # moving too much
                                gesture_score -= 20
                                feedback.append("Slow down hand movements!")
                            elif recent_avg_movement < 0.01:  # very stable
                                gesture_score += 5
                
                self.previous_hand_positions = current_positions.copy()
            
            # bonus for both hands visible
            if len(hand_landmarks) == 2:
                gesture_score += 15
                feedback.append("Both hands visible - excellent!")
            elif len(hand_landmarks) == 1:
                gesture_score += 5
                feedback.append("One hand visible")
            
            gesture_score = max(0, min(100, gesture_score))
            
            # final feedback
            if gesture_score >= 90:
                feedback = ["Perfect hand gestures!"]
            elif gesture_score >= 80:
                feedback = ["Excellent hand positioning!"]
            elif gesture_score >= 70:
                feedback = ["Good hand gestures"]
            elif gesture_score >= 50:
                if not feedback:
                    feedback = ["Fair gestures, some improvement needed"]
            else:
                if not feedback:
                    feedback = ["Poor gestures - major improvements needed"]
            
            return gesture_score, feedback
            
        except Exception as e:
            return 0, ["Unable to analyze gestures - no hands detected"]
    
    def are_hands_associated_with_person(self, pose_landmarks, hand_landmarks):
        # check if hands belong to the person we detected
        if not pose_landmarks or not hand_landmarks:
            return False
        
        try:
            # get shoulder positions
            left_shoulder = pose_landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            right_shoulder = pose_landmarks.landmark[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            
            shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
            shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2
            shoulder_width = abs(right_shoulder.x - left_shoulder.x)
            
            # check each hand to see if it belongs to this person
            valid_hands = []
            for hand in hand_landmarks:
                wrist = hand.landmark[self.mp_hands.HandLandmark.WRIST]
                
                distance_x = abs(wrist.x - shoulder_center_x)
                distance_y = abs(wrist.y - shoulder_center_y)
                
                # hand should be near the person's body
                if (distance_x <= shoulder_width * 2.0 and
                    wrist.y >= shoulder_center_y - 0.1 and
                    wrist.y <= shoulder_center_y + 0.6):
                    valid_hands.append(hand)
            
            return valid_hands if valid_hands else None
            
        except Exception as e:
            return None
    
    def count_people_in_frame(self, pose_results, face_results):
        # figure out how many people are in the camera view
        people_count = 0
        detection_methods = []
        
        # pose only detects 1 person max
        if pose_results.pose_landmarks:
            people_count = max(people_count, 1)
            detection_methods.append("pose")
        
        # face detection can find multiple people
        if face_results.multi_face_landmarks:
            face_count = len(face_results.multi_face_landmarks)
            people_count = max(people_count, face_count)
            detection_methods.append(f"{face_count} face(s)")
        
        return people_count, detection_methods
    
    def draw_feedback(self, image, posture_score, posture_feedback, 
                     eye_contact_score, eye_feedback, gesture_score, gesture_feedback,
                     warning_message=""):
        # put feedback text on the image
        height, width, _ = image.shape
        
        # dark background for text
        overlay = image.copy()
        feedback_height = 250 if warning_message else 200
        cv2.rectangle(overlay, (10, 10), (width - 10, feedback_height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, image, 0.3, 0, image)
        
        y_offset = 40
        if warning_message:
            cv2.putText(image, warning_message, (20, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            y_offset = 60
        
        cv2.putText(image, "Body Language Analysis", (20, y_offset), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # color code the scores
        posture_color = (0, 255, 0) if posture_score >= 70 else (0, 255, 255) if posture_score >= 50 else (0, 0, 255)
        cv2.putText(image, f"Posture: {posture_score:.0f}%", (20, y_offset + 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, posture_color, 2)
        
        eye_color = (0, 255, 0) if eye_contact_score >= 70 else (0, 255, 255) if eye_contact_score >= 50 else (0, 0, 255)
        cv2.putText(image, f"Eye Contact: {eye_contact_score:.0f}%", (20, y_offset + 55), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, eye_color, 2)
        
        gesture_color = (0, 255, 0) if gesture_score >= 70 else (0, 255, 255) if gesture_score >= 50 else (0, 0, 255)
        cv2.putText(image, f"Gestures: {gesture_score:.0f}%", (20, y_offset + 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, gesture_color, 2)
        
        # overall score
        overall_score = (posture_score + eye_contact_score + gesture_score) / 3
        overall_color = (0, 255, 0) if overall_score >= 70 else (0, 255, 255) if overall_score >= 50 else (0, 0, 255)
        cv2.putText(image, f"Overall: {overall_score:.0f}%", (20, y_offset + 110), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, overall_color, 2)
        
        # show feedback messages
        feedback_y_offset = y_offset + 140
        all_feedback = posture_feedback + eye_feedback + gesture_feedback
        for feedback in all_feedback[:3]:  # max 3 messages
            cv2.putText(image, feedback, (20, feedback_y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            feedback_y_offset += 20
    
    def run_analysis(self):
        # main webcam loop
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("Error: Could not open webcam")
            return
        
        print("Body Language Analysis Started!")
        print("Press 'q' to quit, 's' to save current frame")
        print("Note: Only one person should be in frame for accurate analysis")
        print("Debug: Multi-person detection will be logged to console")
        
        frame_count = 0
        
        while cap.isOpened():
            success, image = cap.read()
            if not success:
                print("Ignoring empty camera frame.")
                continue
            
            frame_count += 1
            
            # flip for mirror effect
            image = cv2.flip(image, 1)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # run mediapipe detections
            pose_results = self.pose.process(image_rgb)
            face_results = self.face_mesh.process(image_rgb)
            hand_results = self.hands.process(image_rgb)
            
            # check for multiple people
            people_count, detection_methods = self.count_people_in_frame(pose_results, face_results)
            
            # debug output sometimes
            if frame_count % 30 == 0:
                print(f"Frame {frame_count}: People detected: {people_count}, Methods: {detection_methods}")
                if hand_results.multi_hand_landmarks:
                    print(f"  Hands detected: {len(hand_results.multi_hand_landmarks)}")
            
            multiple_people_warning = ""
            if people_count > 1:
                methods_str = " + ".join(detection_methods)
                multiple_people_warning = f"WARNING: {people_count} people detected ({methods_str})"
                if frame_count % 10 == 0:
                    print(f"ALERT: {multiple_people_warning}")
            
            # draw pose landmarks only if one person
            if pose_results.pose_landmarks and people_count <= 1:
                self.mp_drawing.draw_landmarks(
                    image, pose_results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=self.mp_drawing_styles.get_default_pose_landmarks_style())
            
            # only use hands that belong to the detected person
            valid_hands = None
            if hand_results.multi_hand_landmarks and pose_results.pose_landmarks and people_count <= 1:
                valid_hands = self.are_hands_associated_with_person(
                    pose_results.pose_landmarks, hand_results.multi_hand_landmarks)
                
                if valid_hands:
                    for hand_landmarks in valid_hands:
                        self.mp_drawing.draw_landmarks(
                            image, hand_landmarks, self.mp_hands.HAND_CONNECTIONS,
                            self.mp_drawing_styles.get_default_hand_landmarks_style(),
                            self.mp_drawing_styles.get_default_hand_connections_style())
            
            # analyze stuff only if one person
            if people_count <= 1:
                posture_score, posture_feedback = 0, ["No person detected"]
                if pose_results.pose_landmarks:
                    posture_score, posture_feedback = self.analyze_posture(pose_results.pose_landmarks.landmark)
                
                eye_contact_score, eye_feedback = 0, ["No face detected"]
                if face_results.multi_face_landmarks and len(face_results.multi_face_landmarks) == 1:
                    eye_contact_score, eye_feedback = self.analyze_eye_contact(
                        face_results.multi_face_landmarks[0], image.shape)
                
                gesture_score, gesture_feedback = self.analyze_gestures(valid_hands)
                
            else:
                # multiple people - set everything to 0
                posture_score, posture_feedback = 0, [f"Multiple people detected ({people_count})"]
                eye_contact_score, eye_feedback = 0, [f"Multiple people detected ({people_count})"]
                gesture_score, gesture_feedback = 0, [f"Multiple people detected ({people_count})"]
            
            self.draw_feedback(image, posture_score, posture_feedback,
                             eye_contact_score, eye_feedback, gesture_score, gesture_feedback,
                             multiple_people_warning)
            
            cv2.imshow('Body Language Analysis', image)
            
            key = cv2.waitKey(5) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"body_language_analysis_{timestamp}.jpg"
                cv2.imwrite(filename, image)
                print(f"Screenshot saved as {filename}")
        
        cap.release()
        cv2.destroyAllWindows()

def main():
    # start the whole thing
    analyzer = BodyLanguageAnalyzer()
    analyzer.run_analysis()

if __name__ == "__main__":
    main()
