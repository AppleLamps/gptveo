# Veo 2.0 Text-to-Video Generation Pipeline

This Python+Streamlit application allows you to generate high-quality AI-generated videos using **Google Veo 2.0** (via Vertex AI) and download or preview the results directly from **Google Cloud Storage (GCS)**.

---

## ✅ What This App Does

### 1. **Interactive Prompting UI**
- Users enter text prompts describing a desired video
- Optionally adjust video duration and aspect ratio
- Includes prompt history and examples for inspiration

### 2. **Backend Integration with Vertex AI**
- Uses Google service account credentials securely via `st.secrets`
- Submits a long-running video generation job to the Veo model using `predictLongRunning`
- Polls the job status with `fetchPredictOperation`

### 3. **Automatic GCS Bucket Handling**
- Checks if the defined GCS bucket exists
- Automatically creates it if missing
- Stores video results in a subfolder

### 4. **Secure Download and Playback**
- Once the video is ready, it:
  - Extracts the GCS URI of the `.mp4`
  - Downloads it using `google-cloud-storage`
  - Plays it inside the Streamlit app
  - Provides download buttons and metadata

### 5. **Video Library Tab**
- Lists up to 10 previously generated videos
- Supports filtering, sorting, and playback of recent assets from GCS

---

## 🔒 Required Setup

### Google Cloud Prerequisites
- Enable:
  - Vertex AI API
  - Cloud Storage API
- Create a **service account** with:
  - `Vertex AI User`
  - `Storage Object Admin`
- Share write access to your bucket with:
  - `cloud-lvm-video-server@prod.google.com`

### Local `.streamlit/secrets.toml`
```toml
[gcp]
project_id = "your-gcp-project"
private_key = "..."
client_email = "...@...iam.gserviceaccount.com"
... (full service account fields)
```

---

## 🧠 Key Variables

| Variable              | Purpose                                        |
|-----------------------|------------------------------------------------|
| `PROJECT_ID`          | GCP Project ID                                |
| `MODEL_ID`            | Veo model version                             |
| `GCS_BUCKET_NAME`     | GCS bucket name (must be unique)              |
| `GCS_SUBFOLDER`       | Subfolder for video outputs                   |
| `duration`, `prompt`  | Streamlit form inputs                         |
| `access_token`        | OAuth token used in API requests              |

---

## 📦 Requirements

Dependencies listed in `requirements.txt`:
```txt
streamlit
requests
google-auth
google-auth-oauthlib
google-cloud-storage
google-api-core
```

---

## 🛠 Deployment (Streamlit Cloud)
1. Push project to GitHub
2. Set up app at https://streamlit.io/cloud
3. Add your `.streamlit/secrets.toml`
4. Streamlit Cloud will install requirements and launch automatically

---

## ✨ Future Feature Ideas
- Prompt templates and saved sessions
- Image-to-video support
- Multiple sample generation
- Support for multiple GCS buckets
- User login / tracking

---

Let us know if you’d like this turned into a published Streamlit component or embedded in a larger AI workflow.

