package com.example.simultaneous.ui

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import com.example.simultaneous.data.AudioEngine
import com.example.simultaneous.data.RealtimeClient
import com.example.simultaneous.data.VadProcessor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application), RealtimeClient.Listener {

    // Configuration
    // private val targetLanguage = "English" // Moved to dynamic loading

    // Components
    private val audioEngine = AudioEngine()
    private val vadProcessor = VadProcessor()
    private val client = RealtimeClient(this)

    // State
    private val _status = MutableLiveData("Disconnected")
    val status: LiveData<String> = _status

    private val _transcript = MutableLiveData("")
    val transcript: LiveData<String> = _transcript

    private val _translation = MutableLiveData("")
    val translation: LiveData<String> = _translation

    private var isConnected = false
    private var shouldBeConnected = false // User intent to stay connected
    private var processingJob: kotlinx.coroutines.Job? = null

    // Buffers for text
    private var transcriptBuffer = StringBuilder()
    private var translationBuffer = StringBuilder()

    fun startRecording() {
        // If switch is OFF, don't record
        if (!shouldBeConnected) {
            _status.value = "Please turn on switch"
            return
        }
        
        // If switch is ON but disconnected (Error/Reconnecting), allow recording
        // logic to proceed (UI responsiveness).
        // Optionally trigger immediate reconnect if idle
        if (!isConnected) {
            connectSession()
        }

        audioEngine.startRecording(viewModelScope)
        _status.value = "Speaking"
    }

    fun stopRecording() {
        if (!shouldBeConnected) return
        
        audioEngine.stopRecording()
        // Force commit (safe even if null)
        client.commit()
        
        // Update status based on connection
        if (isConnected) {
            _status.value = "Listening"
        } else {
            _status.value = "Reconnecting..."
        }
    }

    fun connectSession() {
        shouldBeConnected = true
        // Load Settings
        val prefs = getApplication<Application>().getSharedPreferences("app_settings", android.content.Context.MODE_PRIVATE)
        val apiKey = prefs.getString("api_key", "sk-7zp54GI1xp4alaQuydzcxMLhZW47jJAcIJSJksEo7Vfp18Rd") ?: ""
        val baseUrl = prefs.getString("base_url", "ws://jeniya.top") ?: ""
        val modelName = prefs.getString("model_name", "gpt-4o-realtime-preview") ?: ""
        val targetLanguage = prefs.getString("target_language", "English") ?: "English"
        
        // Reset buffers
        transcriptBuffer.clear()
        translationBuffer.clear()
        _transcript.value = ""
        _translation.value = ""
        vadProcessor.reset()

        val instructions = "You are a professional simultaneous interpreter. " +
                "Your task is to translate whatever the user says into $targetLanguage immediately. " +
                "Do not answer the user's question, just translate the content."

        _status.value = "Connecting..."
        client.connect(apiKey, baseUrl, modelName, instructions)
        audioEngine.initPlayer()

        // Start Processing Loop
        if (processingJob == null || processingJob?.isActive == false) {
            processingJob = viewModelScope.launch(Dispatchers.Default) {
                audioEngine.audioInputFlow.collect { bytes ->
                    // 1. Send to WebSocket
                    client.sendAudio(bytes)
                    
                    // 2. VAD for visual feedback only (optional)
                    // We don't use VAD for commit anymore in PTT mode
                }
            }
        }
    }

    fun stopSession() {
        shouldBeConnected = false
        audioEngine.stopRecording()
        client.disconnect()
        _status.value = "Disconnected"
    }

    override fun onCleared() {
        super.onCleared()
        audioEngine.release()
        client.disconnect()
    }

    // --- RealtimeClient Callbacks ---

    override fun onConnected() {
        isConnected = true
        _status.postValue("Listening")
    }

    override fun onDisconnected() {
        isConnected = false
        if (shouldBeConnected) {
            // Auto-reconnect
            _status.postValue("Reconnecting...")
            viewModelScope.launch(Dispatchers.Main) {
                kotlinx.coroutines.delay(2000) // Wait 2s before retry
                if (shouldBeConnected) {
                    connectSession()
                }
            }
        } else {
            _status.postValue("Disconnected")
        }
        audioEngine.stopRecording()
    }

    override fun onError(error: String) {
        Log.e("MainViewModel", "Error: $error")
        _status.postValue("Error: $error")
    }

    override fun onAudioData(data: ByteArray) {
        audioEngine.playAudio(data)
    }

    override fun onTranscriptDelta(text: String) {
        transcriptBuffer.append(text)
        _transcript.postValue(transcriptBuffer.toString())
    }

    override fun onTranslationDelta(text: String) {
        translationBuffer.append(text)
        _translation.postValue(translationBuffer.toString())
    }
}
