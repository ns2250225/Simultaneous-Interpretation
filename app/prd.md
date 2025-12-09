# Product Requirements Document (PRD): Simultaneous Interpretation Android App

## 1. Project Overview
**Project Name**: Simultaneous Interpretation App
**Platform**: Android (Native)
**Language**: Kotlin
**Goal**: Port the existing Python-based real-time translation script (`openai_realtime.py`) to a native Android application. The app will provide real-time speech-to-speech translation using the OpenAI Realtime API (or compatible backends like Doubao), featuring low-latency audio streaming, voice activity detection (VAD), and simultaneous text display of both transcript and translation.

## 2. User Stories
*   **As a user**, I want to input my OpenAI API Key and Base URL so that I can connect to the translation service.
*   **As a user**, I want to select a target language (e.g., English) so the system knows what language to translate into.
*   **As a user**, I want to tap a "Start" button to begin the interpretation session.
*   **As a user**, I want the app to automatically detect when I stop speaking (VAD) and send the audio for translation, so I don't have to press buttons repeatedly.
*   **As a user**, I want to see the text of what I said (Transcript) and the text of the translation (Translation) in real-time.
*   **As a user**, I want to hear the translated audio played back automatically.
*   **As a user**, I want to adjust VAD sensitivity (silence threshold) in settings to match my environment.

## 3. Functional Requirements

### 3.1. Settings & Configuration
The app must allow users to configure the following parameters (stored locally, e.g., using `SharedPreferences` or `DataStore`):
*   **API Configuration**:
    *   `API_KEY`: OpenAI API Key.
    *   `BASE_URL`: Base URL for the WebSocket connection (default: `ws://jeniya.top` or user provided).
    *   `MODEL_NAME`: Model to use (default: `gpt-4o-realtime-preview`).
*   **Translation Settings**:
    *   `TARGET_LANGUAGE`: Target language for translation (default: "English").
    *   `SYSTEM_INSTRUCTIONS`: Custom prompt for the AI interpreter.
*   **Audio/VAD Settings**:
    *   `VAD_THRESHOLD`: Energy threshold for detecting speech (default equivalent to Python's ~500).
    *   `SILENCE_DURATION_MS`: Duration of silence to trigger a commit (default: 500ms).
    *   `MIN_SPEECH_DURATION_MS`: Minimum speech duration to validate a segment (default: 300ms).

### 3.2. Real-time Audio Processing
*   **Audio Input (Microphone)**:
    *   Capture audio using `AudioRecord`.
    *   Format: PCM 16-bit, 24kHz (matches API requirement), Mono.
    *   Buffer Size: 1024 bytes (or appropriate minimum buffer size for Android).
*   **Voice Activity Detection (Client-Side VAD)**:
    *   Implement energy-based VAD on the audio stream.
    *   Calculate RMS/Peak amplitude of incoming PCM chunks.
    *   Logic:
        *   If `amplitude > VAD_THRESHOLD` -> State: **Speaking**.
        *   If `Speaking` and `silence_duration > SILENCE_DURATION_MS` -> Trigger **Commit**.
*   **Audio Output (Speaker)**:
    *   Play received audio chunks using `AudioTrack`.
    *   Format: PCM 16-bit, 24kHz, Mono.
    *   Handle `response.audio.delta` events from WebSocket.

### 3.3. WebSocket Communication
*   **Connection**:
    *   Use `OkHttp` or a native WebSocket library.
    *   URL: `{BASE_URL}/v1/realtime?model={MODEL_NAME}`.
    *   Headers:
        *   `Authorization: Bearer {API_KEY}`
        *   `OpenAI-Beta: realtime=v1`
*   **Protocol Flow**:
    1.  **Connect**: Establish WebSocket connection.
    2.  **Session Update**: Send `session.update` event with instructions, voice settings, and turn detection mode.
    3.  **Streaming**:
        *   Continuously send `input_audio_buffer.append` events with Base64 encoded PCM data.
        *   When VAD triggers commit: Send `input_audio_buffer.commit` and `response.create`.
    4.  **Receiving**: Listen for events:
        *   `response.audio.delta`: Append to audio player buffer.
        *   `response.audio_transcript.delta`: Append to **Translation** text view.
        *   `response.input_audio_transcription.delta`: Append to **Transcript** text view.
        *   `response.done`: Handle end of turn.

### 3.4. User Interface (UI)
*   **Main Screen**:
    *   **Status Bar**: Shows connection status (Disconnected, Connecting, Listening, Speaking, Playing).
    *   **Transcript Area (Top/Left)**: Displays user's recognized speech (yellow/distinct color). Auto-scrolls.
    *   **Translation Area (Bottom/Right)**: Displays AI's translation (blue/distinct color). Auto-scrolls.
    *   **Controls**:
        *   Floating Action Button (FAB) or large button for **Start/Stop**.
        *   Settings Icon (Toolbar).
*   **Settings Screen**:
    *   Input fields for API Key, URL, Model, Target Language.
    *   Sliders/Inputs for VAD Threshold and Silence Duration.

## 4. Technical Architecture

### 4.1. Tech Stack
*   **Language**: Kotlin
*   **Minimum SDK**: API Level 26 (Android 8.0) or higher (for better audio APIs).
*   **Architecture**: MVVM (Model-View-ViewModel).
    *   **Repository**: Manages WebSocket connection and data parsing.
    *   **ViewModel**: Handles UI state (text, status) and business logic (VAD state machine).
    *   **View (Activity/Fragment)**: Renders UI and handles permissions.
*   **Concurrency**: Kotlin Coroutines (`Dispatchers.IO` for network/audio, `Dispatchers.Main` for UI).

### 4.2. Key Libraries
*   **Networking**: `OkHttp` (for WebSocket).
*   **JSON Parsing**: `Kotlinx Serialization` or `Gson`.
*   **Dependency Injection**: `Hilt` or manual DI (keep it simple).
*   **Permission Handling**: AndroidX Activity Result API (for `RECORD_AUDIO`).

### 4.3. Data Flow Diagram
1.  **Mic** -> `AudioRecord` -> **Byte Array**
2.  **Byte Array** -> **VAD Processor** (Checks threshold)
3.  **Byte Array** -> **Base64** -> **WebSocket Repository** -> `input_audio_buffer.append`
4.  **VAD Processor** (Silence Detected) -> **WebSocket Repository** -> `input_audio_buffer.commit`
5.  **WebSocket** (Receive) -> **Event Dispatcher**:
    *   `audio.delta` -> **AudioPlayer** (`AudioTrack`) -> **Speaker**
    *   `text.delta` -> **ViewModel** -> **LiveData/StateFlow** -> **UI**

## 5. Implementation Roadmap
1.  **Project Setup**: Initialize Android project with permissions (`INTERNET`, `RECORD_AUDIO`).
2.  **Audio Engine**: Implement `AudioRecorder` and `AudioPlayer` classes. Verify PCM read/write.
3.  **WebSocket Client**: Implement `RealtimeClient` using OkHttp. Handle connection and auth.
4.  **VAD Logic**: Port the Python VAD logic (energy calculation, state machine) to Kotlin.
5.  **Data Integration**: Connect Audio Input -> WebSocket -> Audio Output.
6.  **UI Development**: Build the Main and Settings screens.
7.  **Testing**: Verify latency, audio quality, and connection stability.

## 6. Edge Cases & Error Handling
*   **Network Loss**: Auto-reconnect or show error message.
*   **Permission Denied**: Gracefully handle missing microphone permission.
*   **API Errors**: Display error messages returned by the API (e.g., quota exceeded).
*   **Audio Focus**: Pause playback if another app requests audio focus (optional but recommended).

## 7. Notes from Python Prototype
*   **Sample Rate**: Ensure 24kHz is strictly used; otherwise, audio will sound pitched up/down.
*   **Buffer Management**: Python uses incremental buffering for text (`_append_incremental`). Android UI should handle partial updates efficiently (e.g., just appending the delta or updating the last line).
*   **SSL/Certificates**: The Python script required custom SSL context. Android's OkHttp usually handles SSL well, but `android:usesCleartextTraffic="true"` might be needed if using `ws://` or self-signed certs (though `wss://` is standard).

