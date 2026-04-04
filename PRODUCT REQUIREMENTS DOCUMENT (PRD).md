PRODUCT REQUIREMENTS DOCUMENT (PRD)
Project Name: RehabAI (Codename: NAKSHATRA-01)
Hackathon: A.P. Shah Institute of Technology - 24Hr Tech Hackathon
Domain: Healthcare (AI-powered physical & cognitive rehabilitation tracking)

1. Product Overview
RehabAI is an interactive, dual-interface web platform that connects clinical oversight with elder-friendly, at-home rehabilitation. It replaces confusing medical dashboards with an immersive "Scrollytelling" interface, utilizing a 3D glass anatomy model and real-time browser-based AI (MediaPipe) to track patient recovery.

The Core Loop:

Caregiver securely registers, adds a patient via a medical questionnaire, and generates a unique access token.

Patient logs in using only the token (zero friction).

Patient performs AI-guided physical/cognitive exercises via the cinematic 3D interface.

Caregiver monitors real-time recovery data through a high-density clinical dashboard.

2. Design System (The "Nakshatra" UI Tokens)
All interfaces must strictly adhere to this visual architecture to ensure the "unreal" cinematic feel while maintaining accessibility for elderly users.

Color Palette:

Background Void: #08090F (Deep Space)

Card Surfaces (Glassmorphism): rgba(255,255,255,0.03) with backdrop-filter: blur(20px) and 1px subtle borders.

Accent Gold (Healing/Success): #C9A84C

Accent Blue (Active/Data): #4A6FA5

Error/Warning: #C47474

Text Primary: #F0EDE6 (Warm White)

Typography:

Hero/Headings: Cormorant Garamond (Thin Italic, elegant, massive scale)

UI/Body: DM Sans (Clean, legible, elder-friendly)

Data/Code/Tokens: DM Mono (Precise, clinical, all-caps)

3. User Roles & Authentication Architecture
3.1 Role: Caregiver / Clinician
Auth Method: Email and Password (Sign Up / Log In).

Permissions: Add patients, view aggregate patient list, view detailed clinical data per patient.

3.2 Role: Patient (Elderly)
Auth Method: Token-Only Login. No email, no password.

Permissions: Read-only access to their specific 3D rehabilitation hub and write-access to their own session data via the AI tracker.

4. Page Architecture & Screen Workflows
Page 00: The Cinematic Landing (Public)
Role: The "wow" factor for judges and users, explaining the problem/solution before authentication.

UI/UX (Scrollytelling with GSAP):

Hero: Deep space #08090F background with animated starfield canvas. Massive Cormorant Garamond text: "RehabAI".

Scroll 1 (The Problem): Text fades in organically: "Rehabilitation is lonely. Recovery is invisible. We changed that."

Scroll 2 (The Solution): Camera dollies into a preview of the Three.js Glass Anatomy model and the MediaPipe skeletal overlay.

Scroll 3 (The Split): The scroll ends at the Identity Gateway (Page 01) with two massive glassmorphic pathways.

Page 01: The Identity Gateway (Auth / Login)
Role: Frictionless routing based on user type.

UI/UX (Pattern: L04 Split Layout):

Left Side (Caregiver): Standard email/password form with glassmorphic inputs. Links to "Create Caregiver Account".

Right Side (Patient): A massive, centered DM Mono input box asking for the specific Access Token. Big gold CTA pill: [ ENTER REHAB ].

Page 02: Caregiver Dashboard & Patient Roster
Role: The control center for clinicians to view multiple patients.

UI/UX (Pattern: L02 Bento Grid):

Top Row: Global metrics (e.g., Total Active Patients, Overall Compliance Rate).

Main Grid: Glass cards representing each patient. Shows Name, Days Post-Op, and a DM Mono status chip ([01 · ON TRACK] or [02 · MISSED SESSION]).

Action: Floating CTA [ + Add New Patient ] which triggers Page 03.

Page 03: Caregiver "Add Patient" Flow
Role: Collect medical baseline data and generate the authentication token.

UI/UX: A modal or slide-over panel with a clean, high-contrast form asking:

Patient Name & Age.

Surgery Type / Target Joint (e.g., Right Knee, Left Shoulder).

Days Post-Op (Sets the baseline difficulty for the AI).

Cognitive Baseline (Sets the sequence length for memory tests).

Output: Upon submission, the system generates and displays a unique 6-character token (e.g., R7-K92) in massive DM Mono text for the caregiver to share with the patient.

Page 04: Patient Scrollytelling Anatomy Hub
Role: The elder-friendly dashboard replacing traditional menus.

UI/UX (Three.js Full-Screen Canvas):

Visual: Translucent glass human body floating in the void.

Interaction: User scrolls down. The GSAP camera dollies into the affected joint (pulsing blue #4A6FA5).

Content: A floating bento card fades in: "Today's Knee Mobility: 15 Reps."

Action: Massive Gold Button: [ START SESSION ].

Page 05: Active AI Rehab Session
Role: The technical core of the application (MediaPipe & Cognitive tracking).

UI/UX (Pattern: L04 Split Screen):

Physical (MediaPipe): Left side shows browser webcam feed with pose-estimation skeletal overlay. Right side features massive DM Mono real-time feedback chips ([ BEND LOWER ]) and a giant SVG circular progress ring tracking completed reps.

Cognitive (Memory Constellation): Left side shows the Three.js head where star nodes light up in a sequence. Right side provides massive tap targets for the patient to repeat the sequence.

Page 06: Clinical Insight Grid
Role: Deep data visualization accessed by the Caregiver by clicking a patient on Page 02.

UI/UX (High-density Bento Grid):

Charts: Line graphs mapping Joint Angle Progress over time and Cognitive Accuracy %.

Typography: Strictly DM Mono for all data labels to emphasize clinical authority to the AIML judges.

5. Technical Execution Plan (24-Hour Scope)
Frontend Tasks (You & Me):

Build the GSAP/Lenis Scrollytelling landing page.

Build the dual-auth Identity Gateway.

Implement the Three.js Glass Anatomy canvas (visual focus).

Build the L02 Bento Grid for the Caregiver Dashboard.

Integrate MediaPipe Pose logic into the Active Rehab React component.

Backend Tasks (Teammate Action Items):

Set up database (SQLite or PostgreSQL via Supabase/Railway).

Create Caregiver Auth endpoints (JWT/Session).

Create POST /patients endpoint: Accepts the questionnaire data, generates a random 6-character alphanumeric string, saves to DB, and returns the token.

Create POST /patient-login endpoint: Validates the token and returns the specific patient's ID and prescribed exercises.

Create POST /sessions endpoint: Saves the angle data/reps from the MediaPipe frontend into the database for the Caregiver dashboard to render.