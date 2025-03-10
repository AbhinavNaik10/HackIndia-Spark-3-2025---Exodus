from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os
from dotenv import load_dotenv
import json
import time
import google.generativeai as genai

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/presentations',
          'https://www.googleapis.com/auth/drive']

# Load environment variables
load_dotenv()

def get_google_credentials():
    """Get or refresh Google API credentials"""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', 
                SCOPES,
                redirect_uri='http://localhost:8080/oauth2callback'
            )
            creds = flow.run_local_server(
                port=8080,
                prompt='consent',
                access_type='offline'
            )
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def generate_slide_content(topic, num_slides, style):
    """Generate slide content using Gemini AI"""
    try:
        # Configure Gemini AI
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        
        # List available models
        print("\nAvailable models:")
        for m in genai.list_models():
            print(f"- {m.name}")
        
        # Use gemini-pro model
        model = genai.GenerativeModel('gemini-2.0-flash-thinking-exp-1219')
        
        prompt = f"""You are a professional presentation creator. Create a {style} presentation about {topic} with exactly {num_slides} slides.
        
        Respond ONLY with a JSON object in this exact format, nothing else:
        {{
            "title": "The main presentation title",
            "slides": [
                {{
                    "title": "First Slide Title",
                    "content": [
                        "First bullet point",
                        "Second bullet point",
                        "Third bullet point"
                    ],
                    "notes": "Speaker notes for this slide"
                }},
                ... more slides ...
            ]
        }}
        
        Requirements:
        1. Response must be valid JSON
        2. Each slide should have 2-4 bullet points
        3. Make content engaging and professional
        4. Include brief speaker notes for each slide
        5. Ensure proper JSON formatting with no trailing commas"""

        # Generate content
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up the response to ensure it's valid JSON
        if not response_text.startswith('{'):
            # Try to find the JSON object
            start_idx = response_text.find('{')
            if start_idx != -1:
                response_text = response_text[start_idx:]
                # Find the matching closing brace
                brace_count = 0
                for i, char in enumerate(response_text):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            response_text = response_text[:i+1]
                            break

        print(f"\nRaw response:\n{response_text}")
        
        try:
            content = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {str(e)}")
            # Create a basic structure if parsing fails
            content = {
                "title": f"{topic.capitalize()} Presentation",
                "slides": [
                    {
                        "title": "Introduction",
                        "content": [
                            f"Overview of {topic}",
                            "Key points to be discussed",
                            "Presentation objectives"
                        ],
                        "notes": "Welcome to the presentation"
                    }
                ]
            }
            # Add more basic slides if needed
            while len(content["slides"]) < num_slides:
                content["slides"].append({
                    "title": f"Slide {len(content['slides']) + 1}",
                    "content": [
                        "Point 1",
                        "Point 2",
                        "Point 3"
                    ],
                    "notes": "Additional slide content"
                })
        
        print(f"\nProcessed content:\n{json.dumps(content, indent=2)}")
        return content
            
    except Exception as e:
        print(f"Error generating content: {str(e)}")
        raise

def create_presentation(content, style, topic):
    """Create Google Slides presentation"""
    try:
        # Get Google API credentials
        creds = get_google_credentials()
        service = build('slides', 'v1', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Create a new presentation
        presentation = {
            'title': f"{topic} - {style.capitalize()} Presentation"
        }
        presentation = service.presentations().create(body=presentation).execute()
        presentation_id = presentation.get('presentationId')
        
        # Get the default slide IDs to delete them
        slides = service.presentations().get(
            presentationId=presentation_id
        ).execute().get('slides')
        
        # Delete default slides
        if slides:
            requests = [
                {
                    'deleteObject': {
                        'objectId': slide.get('objectId')
                    }
                } for slide in slides
            ]
            service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()
        
        # Create slides
        requests = []
        
        # Title slide
        requests.append({
            'createSlide': {
                'slideLayoutReference': {
                    'predefinedLayout': 'TITLE'
                },
                'placeholderIdMappings': [
                    {
                        'layoutPlaceholder': {
                            'type': 'TITLE'
                        },
                        'objectId': 'title'
                    },
                    {
                        'layoutPlaceholder': {
                            'type': 'SUBTITLE'
                        },
                        'objectId': 'subtitle'
                    }
                ]
            }
        })
        
        requests.append({
            'insertText': {
                'objectId': 'title',
                'text': content['title']
            }
        })
        
        requests.append({
            'insertText': {
                'objectId': 'subtitle',
                'text': f"{style.capitalize()} Presentation"
            }
        })
        
        # Content slides
        for slide in content['slides']:
            # Create slide
            slide_id = f"slide_{len(requests)}"
            title_id = f"title_{len(requests)}"
            body_id = f"body_{len(requests)}"
            
            requests.append({
                'createSlide': {
                    'slideLayoutReference': {
                        'predefinedLayout': 'TITLE_AND_BODY'
                    },
                    'objectId': slide_id,
                    'placeholderIdMappings': [
                        {
                            'layoutPlaceholder': {
                                'type': 'TITLE'
                            },
                            'objectId': title_id
                        },
                        {
                            'layoutPlaceholder': {
                                'type': 'BODY'
                            },
                            'objectId': body_id
                        }
                    ]
                }
            })
            
            # Add title
            requests.append({
                'insertText': {
                    'objectId': title_id,
                    'text': slide['title']
                }
            })
            
            # Add content
            bullet_points = '\n• '.join(slide['content'])
            requests.append({
                'insertText': {
                    'objectId': body_id,
                    'text': f"• {bullet_points}"
                }
            })
            
            # Add speaker notes if available
            if 'notes' in slide:
                requests.append({
                    'createSpeakerNotesText': {
                        'objectId': f"notes_{len(requests)}",
                        'slideObjectId': slide_id,
                        'text': slide['notes']
                    }
                })
        
        # Execute the requests
        service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()
        
        # Get presentation URL
        presentation_url = f"https://docs.google.com/presentation/d/{presentation_id}"
        print(f"\nPresentation created successfully!")
        print(f"You can access it at: {presentation_url}")
        
        # Download as PPTX
        export_url = f"https://docs.google.com/presentation/d/{presentation_id}/export/pptx"
        filename = f"{topic.replace(' ', '_').lower()}_presentation.pptx"
        
        # Use Drive API to export and download
        request = drive_service.files().export_media(
            fileId=presentation_id,
            mimeType='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
        
        with open(filename, 'wb') as f:
            f.write(request.execute())
        
        print(f"Presentation downloaded as: {filename}")
        return filename, presentation_url
        
    except Exception as e:
        print(f"Error creating presentation: {str(e)}")
        raise

def main():
    print("Welcome to the Google Slides Presentation Generator!")
    print("-----------------------------------------------")
    
    # Check for API keys
    if not os.getenv('GOOGLE_API_KEY'):
        print("Error: GOOGLE_API_KEY not found in .env file")
        print("Please add your Google API key to the .env file")
        return
    
    if not os.path.exists('credentials.json'):
        print("Error: credentials.json file not found")
        print("Please download your OAuth 2.0 credentials from Google Cloud Console")
        return
    
    # Get user input
    topic = input("\nEnter presentation topic: ")
    while True:
        try:
            num_slides = int(input("Enter number of slides (5-20): "))
            if 5 <= num_slides <= 20:
                break
            print("Please enter a number between 5 and 20")
        except ValueError:
            print("Please enter a valid number")
    
    print("\nSelect presentation style:")
    print("1. Professional")
    print("2. Creative")
    print("3. Minimal")
    print("4. Educational")
    
    style_options = {
        "1": "professional",
        "2": "creative",
        "3": "minimal",
        "4": "educational"
    }
    
    while True:
        style_choice = input("Enter style number (1-4): ")
        if style_choice in style_options:
            style = style_options[style_choice]
            break
        print("Please enter a valid style number")
    
    print("\nGenerating presentation...")
    try:
        # Generate content using Gemini AI
        content = generate_slide_content(topic, num_slides, style)
        
        # Create presentation using Google Slides
        filename, url = create_presentation(content, style, topic)
        
        print("\nSuccess! Your presentation has been generated.")
        print(f"Local file: {os.path.abspath(filename)}")
        print(f"Online version: {url}")
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        print("Failed to generate presentation. Please try again.")

if __name__ == "__main__":
    main() 