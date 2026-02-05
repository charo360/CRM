# CRM Application

A comprehensive CRM application with a Python/FastAPI backend and a React Native/Expo frontend.

## 🚀 Quick Start

The easiest way to run the application is using the provided PowerShell script:

1.  **Right-click** `run_app.ps1` in the root folder.
2.  Select **"Run with PowerShell"**.

This will open two new terminal windows:
*   One for the **Backend** (running on port 8000)
*   One for the **Frontend** (running via Expo)

---

## 🛠️ Manual Setup & Run

If you prefer running components manually or need to set up the project for the first time.

### 1. Backend Setup

**Location:** `./backend`

1.  **Install dependencies:**
    ```bash
    cd backend
    pip install -r requirements.txt
    ```

2.  **Configuration:**
    *   Create a `.env` file in the `backend` folder (based on `.env.example`).
    *   Ensure your `OPENAI_API_KEY` and database credentials are set.
    *   See `backend/ENVIRONMENT_SETUP.md` for details.

3.  **Run Server:**
    ```powershell
    # Windows (PowerShell)
    ./start_server.ps1
    
    # Or manually:
    uvicorn server:app --reload --host 0.0.0.0 --port 8000
    ```

### 2. Frontend Setup

**Location:** `./frontend`

1.  **Install dependencies:**
    ```bash
    cd frontend
    npm install
    ```

2.  **Configuration (⚠️ Important for Android):**
    *   Open `frontend/.env`.
    *   Set `EXPO_PUBLIC_BACKEND_URL` to your computer's **Local IP Address**, NOT `localhost`.
    *   **Reason:** The Android emulator (and physical devices) run on a separate network. `localhost` refers to the *phone itself*, not your computer.
    *   **Example:**
        ```env
        EXPO_PUBLIC_BACKEND_URL=http://10.0.0.139:8000
        ```
    *   To find your IP: Run `ipconfig` in a terminal and look for IPv4 Address.

3.  **Run App:**
    ```bash
    npm start
    ```
    *   Press `a` to open in Android Emulator.
    *   Scan the QR code with Expo Go app for physical device.

---

## 🐛 Troubleshooting

### "Network Error" on Login
*   **Cause:** The frontend cannot reach the backend.
*   **Fix:**
    1.  Check that the backend server is running (port 8000).
    2.  Check `frontend/.env`. Ensure it uses your actual IP address (e.g., `http://192.168.1.5:8000`), NOT `localhost`.
    3.  Restart the frontend (`npm start`) after changing `.env`.
    4.  Ensure your computer and phone are on the *same Wi-Fi network*.

### Server Starts but "AI Draft" fails
*   **Cause:** Missing or invalid OpenAI API Key.
*   **Fix:** Check `backend/.env` and ensure `OPENAI_API_KEY` is set correctly. Run `python check_env.py` in the backend folder to validate.
