import streamlit as st
import time
import requests
import json
from google.oauth2 import service_account
from google.cloud import storage
from google.api_core.exceptions import NotFound
import os
from datetime import datetime

# ==== CONFIGURATION ====
PROJECT_ID = "gen-lang-client-0290195824"
MODEL_ID = "veo-2.0-generate-001"
GCS_BUCKET_NAME = "applelamps-unique-veo-bucket"
GCS_SUBFOLDER = "veo_outputs"

# ==== AUTH (using st.secrets with proper scope) ====
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/devstorage.read_write"
]

credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp"],
    scopes=SCOPES
)

credentials.refresh(Request())
access_token = credentials.token

# ==== BUCKET MANAGEMENT ====
def ensure_bucket_exists(bucket_name):
    client = storage.Client(project=PROJECT_ID, credentials=credentials)
    try:
        client.get_bucket(bucket_name)
    except NotFound:
        client.create_bucket(bucket_name, location="us-central1")

def download_from_gcs(gcs_uri, local_path):
    parts = gcs_uri.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_path = parts[1]
    storage_client = storage.Client(project=PROJECT_ID, credentials=credentials)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)

def list_video_uris(bucket_name, prefix):
    client = storage.Client(project=PROJECT_ID, credentials=credentials)
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    return [f"gs://{bucket_name}/{blob.name}" for blob in blobs if blob.name.endswith(".mp4")]

# ==== VIDEO GENERATION FUNCTION ====
def generate_video(prompt, duration, aspect_ratio):
    ensure_bucket_exists(GCS_BUCKET_NAME)
    gcs_uri = f"gs://{GCS_BUCKET_NAME}/{GCS_SUBFOLDER}/"
    endpoint = (
        f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}"
        f"/locations/us-central1/publishers/google/models/{MODEL_ID}:predictLongRunning"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "instances": [
            {"prompt": prompt}
        ],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "personGeneration": "allow",
            "durationSeconds": duration,
            "sampleCount": 1,
            "storageUri": gcs_uri
        }
    }
    res = requests.post(endpoint, headers=headers, json=payload)
    if res.status_code != 200:
        return None, f"API Error: {res.text}"
    operation_name = res.json()["name"]
    poll_endpoint = (
        f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}"
        f"/locations/us-central1/publishers/google/models/{MODEL_ID}:fetchPredictOperation"
    )
    for _ in range(60):
        poll_res = requests.post(poll_endpoint, headers=headers, json={"operationName": operation_name})
        poll = poll_res.json()
        if poll.get("done"):
            if "error" in poll:
                return None, f"Generation error: {poll['error']}"
            video_uri = poll["response"]["videos"][0]["gcsUri"]
            return video_uri, None
        time.sleep(10)
    return None, "Timeout waiting for video generation"

# ==== STREAMLIT UI ====
st.set_page_config(page_title="Veo 2.0 Video Generator", layout="wide")

# Custom CSS
st.markdown("""
<style>
.main-header {
    background: linear-gradient(to right, #4880EC, #019CAD);
    color: white;
    padding: 1.5rem;
    border-radius: 0.5rem;
    margin-bottom: 1.5rem;
    text-align: center;
}
.subheader {
    background-color: #f8f9fa;
    padding: 0.75rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    border-left: 4px solid #4880EC;
}
.stButton>button {
    width: 100%;
}
.video-card {
    background-color: #f0f2f6;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 1rem;
    border: 1px solid #e0e3e8;
}
.success-message {
    background-color: #d4edda;
    color: #155724;
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
}
.error-message {
    background-color: #f8d7da;
    color: #721c24;
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header"><h1>Veo 2.0 Text-to-Video Generator</h1></div>', unsafe_allow_html=True)

# Initialize session state for prompt if not exists
if 'prompt' not in st.session_state:
    st.session_state.prompt = "A cinematic drone shot over a misty forest at sunrise"

# Create tabs
tab1, tab2 = st.tabs(["Generate New Video", "Video Library"])

# Example prompts
example_prompts = [
    "A cinematic drone shot over a misty forest at sunrise",
    "A futuristic city with flying cars and neon lights",
    "A peaceful beach with gentle waves at sunset",
    "An astronaut walking on the surface of Mars",
]

# Generate tab
with tab1:
    # Function to update prompt
    def set_prompt(text):
        st.session_state.prompt = text

    # Layout with columns
    prompt_col, preview_col = st.columns([1, 1])
    
    with prompt_col:
        st.markdown('<div class="subheader"><h3>Create Your Video</h3></div>', unsafe_allow_html=True)
        
        # Prompt input
        st.markdown("**Enter your prompt:**")
        prompt = st.text_area(
            "Describe what you want to see in your video", 
            value=st.session_state.prompt,
            height=100, 
            key="prompt_input",
            help="Be descriptive! Include details about scenery, lighting, camera movement, etc."
        )
        
        # Example prompts section
        st.markdown("**Try an example prompt:**")
        cols = st.columns(2)
        
        # Create example buttons
        for i, ex_prompt in enumerate(example_prompts):
            if cols[i % 2].button(f"Example {i+1}", key=f"ex_{i}"):
                set_prompt(ex_prompt)
                st.experimental_rerun()
        
        # Video settings
        st.markdown("**Video settings:**")
        settings_col1, settings_col2 = st.columns(2)
        
        with settings_col1:
            duration = st.slider("Duration (seconds)", 1, 8, 5)
        
        with settings_col2:
            aspect_ratio = st.selectbox(
                "Aspect Ratio", 
                ["16:9", "1:1", "9:16"],
                help="16:9 for landscape, 1:1 for square, 9:16 for portrait/mobile"
            )
        
        # Generation button
        generate_btn = st.button("🎬 Generate Video", use_container_width=True)
    
    with preview_col:
        st.markdown('<div class="subheader"><h3>Video Preview</h3></div>', unsafe_allow_html=True)
        
        # Container for results
        result_container = st.container()
        
        if generate_btn:
            with result_container:
                if not prompt.strip():
                    st.warning("Please enter a prompt before generating a video.")
                else:
                    # Progress tracking
                    progress_container = st.container()
                    with progress_container:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Initialization step
                        status_text.text("🔄 Initializing generation...")
                        progress_bar.progress(0.1)
                        time.sleep(0.5)
                        
                        # Generation step
                        status_text.text("✨ Creating your video (this may take 1-2 minutes)...")
                        progress_bar.progress(0.3)
                        
                        # Call generate_video
                        video_uri, error = generate_video(prompt, duration, aspect_ratio)
                        
                        if error:
                            progress_bar.empty()
                            st.error(f"⚠️ Generation failed: {error}")
                        else:
                            # Processing step
                            status_text.text("🎞️ Processing video...")
                            progress_bar.progress(0.8)
                            time.sleep(0.5)
                            
                            # Download step
                            status_text.text("⬇️ Preparing video for preview...")
                            progress_bar.progress(0.9)
                            
                            output_path = "generated_video.mp4"
                            download_from_gcs(video_uri, output_path)
                            
                            # Complete
                            status_text.text("✅ Video generation complete!")
                            progress_bar.progress(1.0)
                            time.sleep(1)
                            
                            # Remove progress indicators
                            progress_container.empty()
                            
                            # Success message
                            st.success("✅ Video generated successfully!")
                            
                            # Video display
                            st.video(output_path)
                            
                            # Download button and metadata
                            dl_col, info_col = st.columns([1, 1])
                            
                            with dl_col:
                                st.download_button(
                                    "⬇️ Download Video", 
                                    data=open(output_path, "rb"), 
                                    file_name="generated_video.mp4",
                                    use_container_width=True
                                )
                            
                            # Video details in expandable section
                            with st.expander("Video Details", expanded=True):
                                st.markdown(f"**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                                st.markdown(f"**Prompt:** {prompt}")
                                st.markdown(f"**Duration:** {duration} seconds")
                                st.markdown(f"**Aspect Ratio:** {aspect_ratio}")
                                st.markdown(f"**GCS URI:** `{video_uri}`")

# Library tab
with tab2:
    st.markdown('<div class="subheader"><h3>Your Generated Videos</h3></div>', unsafe_allow_html=True)
    
    # Search and filter controls
    filter_col1, filter_col2 = st.columns([3, 1])
    
    with filter_col1:
        search_query = st.text_input("🔍 Search videos", placeholder="Enter filename to search...")
    
    with filter_col2:
        sort_by = st.selectbox("Sort by", ["Newest first", "Oldest first"])
    
    # Get video list
    uris = list_video_uris(GCS_BUCKET_NAME, GCS_SUBFOLDER)
    
    # Filter by search query if provided
    if search_query:
        uris = [uri for uri in uris if search_query.lower() in uri.lower()]
    
    # Sort videos
    if sort_by == "Newest first":
        uris = uris[::-1]
    
    # Show videos
    if not uris:
        st.info("📭 No videos found in your library. Generate some videos to see them here!")
    else:
        st.markdown(f"**Showing {len(uris)} videos**")
        
        # Create a container for the video library
        library_container = st.container()
        
        with library_container:
            # Display videos in a grid (limit to 10 for performance)
            max_videos = min(len(uris), 10)
            
            # Create two-column grid layout for videos
            for i in range(0, max_videos, 2):
                cols = st.columns(2)
                
                for j in range(2):
                    idx = i + j
                    if idx < max_videos:
                        with cols[j]:
                            st.markdown(f"<div class='video-card'>", unsafe_allow_html=True)
                            
                            # Get filename from URI
                            filename = uris[idx].split("/")[-1]
                            st.markdown(f"**Video {idx+1}: {filename}**")
                            
                            # Display video
                            temp_file = f"preview_{idx}.mp4"
                            with st.spinner(f"Loading video {idx+1}..."):
                                download_from_gcs(uris[idx], temp_file)
                            st.video(temp_file)
                            
                            # Download button
                            st.download_button(
                                "⬇️ Download", 
                                data=open(temp_file, "rb"), 
                                file_name=filename,
                                key=f"download_{idx}",
                                use_container_width=True
                            )
                            
                            # Expandable section for details
                            with st.expander("Details"):
                                st.markdown(f"**URI:** `{uris[idx]}`")
                                # Try to extract creation date from filename if available
                                try:
                                    file_date = os.path.getctime(temp_file)
                                    st.markdown(f"**Date:** {datetime.fromtimestamp(file_date).strftime('%Y-%m-%d %H:%M')}")
                                except:
                                    pass
                            
                            st.markdown("</div>", unsafe_allow_html=True)
            
            # Show note if there are more videos
            if len(uris) > 10:
                st.info(f"ℹ️ Showing 10 of {len(uris)} videos. Use search to find specific videos.")
