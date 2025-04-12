import streamlit as st
import time
import requests
import json
from google.oauth2 import service_account
from google.cloud import storage
from google.api_core.exceptions import NotFound
import os
from datetime import datetime
import math

# ==== CONFIGURATION ====
PROJECT_ID = "gen-lang-client-0290195824"
MODEL_ID = "veo-2.0-generate-001"
GCS_BUCKET_NAME = "applelamps-unique-veo-bucket"
GCS_SUBFOLDER = "veo_outputs"
VIDEOS_PER_PAGE = 6 # Number of videos to show per page in the library

# Placeholder image (base64 encoded or a URL)
PLACEHOLDER_IMAGE = "https://via.placeholder.com/400x300?text=Video+Preview"  # Example URL

# ==== AUTH (using st.secrets) ====
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/devstorage.read_write"
]

# Function to get credentials safely
@st.cache_resource # Cache credentials for the session
def get_credentials():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp"],
        scopes=SCOPES
    )
    creds.refresh(Request())
    return creds

credentials = get_credentials()
access_token = credentials.token

# ==== BUCKET MANAGEMENT ====
@st.cache_resource # Cache storage client
def get_storage_client():
    return storage.Client(project=PROJECT_ID, credentials=credentials)

storage_client = get_storage_client()

def ensure_bucket_exists(bucket_name):
    try:
        storage_client.get_bucket(bucket_name)
    except NotFound:
        storage_client.create_bucket(bucket_name, location="us-central1")
        st.toast(f"Created GCS bucket: {bucket_name}")

def download_from_gcs(gcs_uri, local_path):
    try:
        parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        blob_path = parts[1]
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.download_to_filename(local_path)
        return True
    except Exception as e:
        st.error(f"Error downloading {gcs_uri}: {e}")
        return False

# Cache the list of URIs for a short time to avoid excessive GCS calls
@st.cache_data(ttl=60) # Cache for 60 seconds
def list_video_uris(bucket_name, prefix):
    try:
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        # Sort blobs by creation time descending (newest first)
        sorted_blobs = sorted(blobs, key=lambda b: b.time_created, reverse=True)
        return [f"gs://{bucket_name}/{blob.name}" for blob in sorted_blobs if blob.name.endswith(".mp4")]
    except Exception as e:
        st.error(f"Error listing videos: {e}")
        return []

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
    try:
        res = requests.post(endpoint, headers=headers, json=payload, timeout=30) # Added timeout
        res.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        return None, f"API Request Error: {e}"

    operation_name = res.json()["name"]
    poll_endpoint = (
        f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}"
        f"/locations/us-central1/publishers/google/models/{MODEL_ID}:fetchPredictOperation"
    )
    # Increased polling time slightly, reduced iterations
    for _ in range(40): # Poll for up to ~6-7 minutes
        try:
            poll_res = requests.post(poll_endpoint, headers=headers, json={"operationName": operation_name}, timeout=15)
            poll_res.raise_for_status()
            poll = poll_res.json()
            if poll.get("done"):
                if "error" in poll:
                    return None, f"Generation error: {poll['error'].get('message', 'Unknown error')}"
                if "response" in poll and "videos" in poll["response"] and poll["response"]["videos"]:
                    video_uri = poll["response"]["videos"][0]["gcsUri"]
                    return video_uri, None
                else:
                    return None, "Generation completed but no video URI found in response."
            time.sleep(10) # Wait before next poll
        except requests.exceptions.RequestException as e:
            # Continue polling even if one poll request fails, but log it
            st.warning(f"Polling request failed: {e}. Retrying...")
            time.sleep(10) # Wait a bit longer after a failed poll
        except Exception as e:
            return None, f"Unexpected error during polling: {e}"

    return None, "Timeout waiting for video generation to complete."

# ==== STREAMLIT UI ====
st.set_page_config(page_title="Veo 2.0 Video Generator", layout="wide")

# Initialize session state variables
if 'prompt' not in st.session_state:
    st.session_state.prompt = "A cinematic drone shot over a misty forest at sunrise"
if 'generating' not in st.session_state:
    st.session_state.generating = False # Track if generation is in progress
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1 # For library pagination

# Custom CSS
st.markdown("""
<style>
/* General */
body {
    font-family: sans-serif;
}

/* Header */
.main-header {
    background: linear-gradient(to right, #4a90e2, #0077b6); /* Updated gradient */
    color: white;
    padding: 1.5rem;
    border-radius: 0.75rem; /* Slightly more rounded */
    margin-bottom: 2rem;
    text-align: center;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
.main-header h1 {
    margin: 0;
    font-weight: 600;
}

/* Subheader */
.subheader {
    background-color: #f8f9fa;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1.5rem; /* Increased margin */
    border-left: 5px solid #4a90e2; /* Updated color */
}
.subheader h3 {
    margin: 0;
    color: #343a40;
}

/* Buttons */
.stButton>button {
    width: 100%;
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    font-weight: 500;
    transition: background-color 0.3s ease, transform 0.1s ease;
}
.stButton>button:hover {
    background-color: #4a90e2; /* Match header color */
    color: white;
}
.stButton>button:active {
    transform: scale(0.98);
}
/* Style the primary generate button differently */
.stButton[kind="primary"]>button {
    background-color: #28a745; /* Green */
    color: white;
}
.stButton[kind="primary"]>button:hover {
    background-color: #218838;
}
.stButton>button:disabled {
    background-color: #cccccc;
    color: #666666;
    cursor: not-allowed;
}

/* Video Card in Library */
.video-card {
    background-color: #ffffff; /* White background */
    border-radius: 0.75rem; /* Match header */
    padding: 1.25rem; /* Increased padding */
    margin-bottom: 1.5rem;
    border: 1px solid #e0e3e8;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    transition: box-shadow 0.3s ease;
}
.video-card:hover {
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}
.video-title {
  font-size: 1rem; /* Slightly smaller */
  font-weight: 600; /* Bolder */
  margin-bottom: 0.75rem; /* Increased margin */
  color: #495057;
  word-wrap: break-word; /* Prevent long filenames from overflowing */
}
.video-date {
    font-size: 0.85rem;
    color: #6c757d;
    margin-bottom: 0.75rem;
}

/* Messages */
.success-message, .error-message, .warning-message, .info-message {
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    border: 1px solid;
}
.success-message { background-color: #d4edda; color: #155724; border-color: #c3e6cb; }
.error-message { background-color: #f8d7da; color: #721c24; border-color: #f5c6cb; }
.warning-message { background-color: #fff3cd; color: #856404; border-color: #ffeeba; }
.info-message { background-color: #d1ecf1; color: #0c5460; border-color: #bee5eb; }

/* Placeholder */
.video-placeholder {
    background-color: #f8f9fa;
    border-radius: 0.5rem;
    padding: 3rem 1rem; /* More padding */
    text-align: center;
    color: #6c757d;
    margin-bottom: 1rem;
    border: 1px dashed #ced4da; /* Dashed border */
    display: flex; /* Center content vertically */
    align-items: center;
    justify-content: center;
    min-height: 200px; /* Ensure it has some height */
}

/* Pagination */
.pagination-container {
    display: flex;
    justify-content: center;
    align-items: center;
    margin-top: 1.5rem;
    gap: 0.5rem; /* Spacing between elements */
}

</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header"><h1>Veo 2.0 Text-to-Video Generator</h1></div>', unsafe_allow_html=True)

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
        prompt_input = st.text_area(
            "Describe the video scene", # Simplified label
            value=st.session_state.prompt,
            height=120, # Slightly taller
            key="prompt_input_area", # Unique key
            help="Be descriptive! Include details about scenery, action, lighting, camera movement, style (e.g., cinematic, watercolor, hyperrealistic)."
        )
        # Update session state if text_area changes
        st.session_state.prompt = prompt_input

        # Example prompts section
        st.markdown("**Or try an example prompt:**")
        cols = st.columns(2)
        for i, ex_prompt in enumerate(example_prompts):
            with cols[i % 2]:
                # Use on_click to set prompt and rerun
                if st.button(label=ex_prompt, key=f"ex_{i}", on_click=set_prompt, args=[ex_prompt], help=f"Use prompt: '{ex_prompt}'"):
                    # Rerun is implicitly handled by Streamlit when on_click changes state
                    pass

        st.divider()

        # Video settings
        st.markdown("**Video settings:**")
        settings_col1, settings_col2 = st.columns(2)
        with settings_col1:
            duration = st.slider("Duration (seconds)", 1, 8, 5, help="Length of the generated video.")
        with settings_col2:
            aspect_ratio = st.selectbox(
                "Aspect Ratio",
                ["16:9", "1:1", "9:16"],
                help="16:9 (Landscape), 1:1 (Square), 9:16 (Portrait/Mobile)"
            )

        # Generation button - Disabled state managed by session_state.generating
        generate_btn = st.button(
            "🎬 Generate Video",
            use_container_width=True,
            type="primary", # Use Streamlit's primary button styling
            disabled=st.session_state.generating, # Disable if generating
            key="generate_button"
        )

    with preview_col:
        st.markdown('<div class="subheader"><h3>Video Preview</h3></div>', unsafe_allow_html=True)
        result_container = st.container() # Keep container for results

        # Display placeholder if not generating and no video is present
        if not st.session_state.generating and 'last_generated_video' not in st.session_state:
             with result_container:
                st.markdown(f"<div class='video-placeholder'>🖼️<br>Your generated video will appear here.</div>", unsafe_allow_html=True)

        # Handle Generation Button Click
        if generate_btn:
            if not st.session_state.prompt.strip():
                st.warning("Please enter a prompt before generating a video.")
                # Clear generating flag if prompt was empty
                st.session_state.generating = False
            else:
                # Set generating flag to True and rerun to disable button
                st.session_state.generating = True
                st.experimental_rerun() # Rerun to update UI (disable button)

        # Show progress and generate video if the generating flag is set
        if st.session_state.generating:
            with result_container: # Display progress within the result container
                progress_bar = st.progress(0)
                status_text = st.empty()
                output_path = "generated_video.mp4" # Define output path

                try:
                    # Initialization step
                    status_text.text("🔄 Initializing generation...")
                    progress_bar.progress(10) # Use 0-100 scale
                    time.sleep(0.5)

                    # Generation step
                    status_text.text("✨ Creating your video (this may take several minutes)...")
                    progress_bar.progress(30)

                    # Call generate_video
                    video_uri, error = generate_video(st.session_state.prompt, duration, aspect_ratio)

                    if error:
                        status_text.empty()
                        progress_bar.empty()
                        st.error(f"⚠️ Generation failed: {error}")
                        st.session_state.pop('last_generated_video', None) # Remove any previous success state
                    else:
                        # Processing step
                        status_text.text("🎞️ Processing video...")
                        progress_bar.progress(80)
                        time.sleep(0.5)

                        # Download step
                        status_text.text("⬇️ Preparing video for preview...")
                        if download_from_gcs(video_uri, output_path):
                            progress_bar.progress(90)
                            # Complete
                            status_text.text("✅ Video generation complete!")
                            progress_bar.progress(100)
                            time.sleep(1)

                            # Clear progress indicators
                            status_text.empty()
                            progress_bar.empty()

                            # Store success state
                            st.session_state.last_generated_video = {
                                "path": output_path,
                                "uri": video_uri,
                                "prompt": st.session_state.prompt,
                                "duration": duration,
                                "aspect_ratio": aspect_ratio,
                                "timestamp": datetime.now()
                            }
                            # Rerun to display the video and details below
                            st.experimental_rerun()
                        else:
                            # Handle download failure
                            status_text.empty()
                            progress_bar.empty()
                            st.error("⚠️ Video generated but failed to download for preview.")
                            st.session_state.pop('last_generated_video', None)

                finally:
                    # IMPORTANT: Always reset the generating flag, even on error
                    st.session_state.generating = False
                    # If no success state was set, rerun to potentially show errors/reset UI
                    if 'last_generated_video' not in st.session_state:
                         st.experimental_rerun()


        # Display the last successfully generated video if it exists
        if not st.session_state.generating and 'last_generated_video' in st.session_state:
            with result_container:
                video_info = st.session_state.last_generated_video
                st.success("✅ Video generated successfully!")
                st.video(video_info["path"])

                # Download button and metadata
                dl_col, _ = st.columns([1, 1]) # Only need download column now
                with dl_col:
                    try:
                        with open(video_info["path"], "rb") as fp:
                            st.download_button(
                                "⬇️ Download Video",
                                data=fp,
                                file_name=os.path.basename(video_info["path"]), # Use actual filename
                                mime="video/mp4",
                                use_container_width=True
                            )
                    except FileNotFoundError:
                        st.error("Could not find video file for download.")

                # Video details in expandable section
                with st.expander("Video Details", expanded=False): # Start collapsed
                    st.markdown(f"**Created:** {video_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    st.markdown(f"**Prompt:** {video_info['prompt']}")
                    st.markdown(f"**Duration:** {video_info['duration']} seconds")
                    st.markdown(f"**Aspect Ratio:** {video_info['aspect_ratio']}")
                    st.markdown(f"**GCS URI:** `{video_info['uri']}`")

# Library tab
with tab2:
    st.markdown('<div class="subheader"><h3>Your Generated Videos</h3></div>', unsafe_allow_html=True)

    # Search and filter controls
    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        search_query = st.text_input("🔍 Search by filename", placeholder="Enter part of a filename...", key="search_library")
    with filter_col2:
        # Sorting is now handled by list_video_uris (newest first)
        st.markdown("**Sorted by:** Newest First") # Indicate default sort

    # Get video list (cached)
    all_uris = list_video_uris(GCS_BUCKET_NAME, GCS_SUBFOLDER)

    # Filter by search query if provided
    if search_query:
        filtered_uris = [uri for uri in all_uris if search_query.lower() in uri.lower()]
    else:
        filtered_uris = all_uris

    # --- Pagination Logic ---
    total_videos = len(filtered_uris)
    if total_videos == 0:
        if search_query:
            st.info(f"📭 No videos found matching '{search_query}'.")
        else:
            st.info("📭 Your video library is empty. Generate some videos first!")
    else:
        total_pages = math.ceil(total_videos / VIDEOS_PER_PAGE)

        # Ensure current page is valid
        if st.session_state.current_page > total_pages:
            st.session_state.current_page = total_pages
        if st.session_state.current_page < 1:
            st.session_state.current_page = 1

        # Pagination controls container
        st.markdown('<div class="pagination-container">', unsafe_allow_html=True)
        
        # "Previous" button
        prev_disabled = st.session_state.current_page <= 1
        if st.button("⬅️ Previous", disabled=prev_disabled, key="prev_page"):
            st.session_state.current_page -= 1
            st.experimental_rerun()

        # Page indicator
        st.markdown(f"Page **{st.session_state.current_page}** of **{total_pages}**")

        # "Next" button
        next_disabled = st.session_state.current_page >= total_pages
        if st.button("Next ➡️", disabled=next_disabled, key="next_page"):
            st.session_state.current_page += 1
            st.experimental_rerun()
            
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(f"*(Showing videos {(st.session_state.current_page - 1) * VIDEOS_PER_PAGE + 1} - {min(st.session_state.current_page * VIDEOS_PER_PAGE, total_videos)} of {total_videos})*")

        # Calculate start and end index for the current page
        start_idx = (st.session_state.current_page - 1) * VIDEOS_PER_PAGE
        end_idx = start_idx + VIDEOS_PER_PAGE
        uris_to_display = filtered_uris[start_idx:end_idx]

        # --- Display Videos ---
        library_container = st.container()
        with library_container:
            # Use 3 columns for better grid layout
            num_columns = 3
            cols = st.columns(num_columns)
            
            for i, uri in enumerate(uris_to_display):
                with cols[i % num_columns]:
                    st.markdown(f"<div class='video-card'>", unsafe_allow_html=True)
                    filename = uri.split("/")[-1]
                    
                    # Display Title
                    st.markdown(f"<div class='video-title'>{filename}</div>", unsafe_allow_html=True)

                    # Attempt to get and display date (from local temp file if exists, else skip)
                    temp_file_path = f"preview_{start_idx + i}.mp4" # Unique temp file per video index
                    file_date_str = "Date unknown"
                    try:
                        # Only getctime if file exists locally (avoids re-download just for date)
                        if os.path.exists(temp_file_path):
                           file_timestamp = os.path.getctime(temp_file_path)
                           file_date_str = datetime.fromtimestamp(file_timestamp).strftime('%Y-%m-%d %H:%M')
                        # If GCS metadata is preferred, you'd need to fetch blob metadata here
                    except Exception:
                        pass # Ignore errors getting date
                    st.markdown(f"<div class='video-date'>{file_date_str}</div>", unsafe_allow_html=True)

                    # Display video (download if needed)
                    video_placeholder = st.empty()
                    try:
                        # Download only if the temp file doesn't exist or is very old
                        needs_download = not os.path.exists(temp_file_path) # Add time check if needed
                        if needs_download:
                             with video_placeholder.spinner(f"Loading video..."):
                                if not download_from_gcs(uri, temp_file_path):
                                     video_placeholder.error("Failed to load video.")
                                     temp_file_path = None # Mark as failed
                        
                        if temp_file_path and os.path.exists(temp_file_path):
                             video_placeholder.video(temp_file_path)
                        elif not needs_download: # If exists but failed earlier
                             video_placeholder.error("Failed to load video.")


                    except Exception as e:
                         video_placeholder.error(f"Error displaying video: {e}")


                    # Download button for the specific video
                    if temp_file_path and os.path.exists(temp_file_path):
                         try:
                              with open(temp_file_path, "rb") as fp:
                                   st.download_button(
                                        "⬇️ Download",
                                        data=fp,
                                        file_name=filename,
                                        mime="video/mp4",
                                        key=f"download_{start_idx + i}", # Ensure unique key per page item
                                        use_container_width=True
                                   )
                         except Exception as e:
                              st.error(f"Download error: {e}")

                    # Details Expander (URI)
                    with st.expander("Details"):
                        st.markdown(f"**GCS URI:** `{uri}`")

                    st.markdown("</div>", unsafe_allow_html=True) # Close video-card div
