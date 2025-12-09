package com.example.simultaneous.data

import android.util.Base64
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class RealtimeClient(
    private val listener: Listener
) {
    interface Listener {
        fun onConnected()
        fun onDisconnected()
        fun onError(error: String)
        fun onAudioData(data: ByteArray)
        fun onTranscriptDelta(text: String)
        fun onTranslationDelta(text: String)
    }

    private var webSocket: WebSocket? = null
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS) // WebSocket requires 0
        .build()

    fun connect(apiKey: String, baseUrl: String, model: String, instructions: String) {
        if (webSocket != null) return

        // Format URL: ws://host/v1/realtime?model=...
        // Note: okhttp handles ws:// and wss://
        val url = "$baseUrl/v1/realtime?model=$model"
        
        Log.d("RealtimeClient", "Connecting to $url")

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $apiKey")
            .addHeader("OpenAI-Beta", "realtime=v1")
            .build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d("RealtimeClient", "Connected")
                listener.onConnected()
                sendSessionUpdate(webSocket, instructions)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.d("RealtimeClient", "Closing: $reason")
                webSocket.close(1000, null)
                listener.onDisconnected()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e("RealtimeClient", "Failure: ${t.message}")
                listener.onError(t.message ?: "Unknown error")
                listener.onDisconnected()
            }
        })
    }

    private fun sendSessionUpdate(ws: WebSocket, instructions: String) {
        try {
            val session = JSONObject()
            session.put("modalities", org.json.JSONArray().put("text").put("audio"))
            session.put("instructions", instructions)
            session.put("voice", "alloy")
            session.put("input_audio_format", "pcm16")
            session.put("output_audio_format", "pcm16")
            
            val turnDetection = JSONObject()
            turnDetection.put("type", "server_vad") // We use server VAD or manual?
            // User requested "client side VAD" logic in Python script to trigger commits.
            // But if we use server_vad, server decides when to reply.
            // In Python script: "turn_detection": {"type": "server_vad"}
            // AND manual commits are sent.
            // Let's keep it as server_vad for safety, but we will send manual commits too.
            session.put("turn_detection", turnDetection)
            
            val event = JSONObject()
            event.put("type", "session.update")
            event.put("session", session)
            
            ws.send(event.toString())
        } catch (e: Exception) {
            Log.e("RealtimeClient", "Error sending session update", e)
        }
    }

    private fun handleMessage(text: String) {
        try {
            val event = JSONObject(text)
            val type = event.optString("type")

            when (type) {
                "response.audio.delta" -> {
                    val delta = event.optString("delta")
                    if (delta.isNotEmpty()) {
                        val bytes = Base64.decode(delta, Base64.DEFAULT)
                        listener.onAudioData(bytes)
                    }
                }
                "response.audio_transcript.delta" -> {
                    val delta = event.optString("delta")
                    listener.onTranslationDelta(delta)
                }
                "response.input_audio_transcription.delta" -> {
                    val delta = event.optString("delta")
                    listener.onTranscriptDelta(delta)
                }
                "response.output_text.delta" -> {
                     val delta = event.optString("delta")
                     listener.onTranslationDelta(delta)
                }
                "error" -> {
                    val error = event.optJSONObject("error")?.optString("message") ?: "Unknown API Error"
                    listener.onError("API: $error")
                }
            }
        } catch (e: Exception) {
            Log.e("RealtimeClient", "Error parsing message", e)
        }
    }

    fun sendAudio(bytes: ByteArray) {
        if (webSocket == null) return
        try {
            val base64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
            val event = JSONObject()
            event.put("type", "input_audio_buffer.append")
            event.put("audio", base64)
            webSocket?.send(event.toString())
        } catch (e: Exception) {
            Log.e("RealtimeClient", "Error sending audio", e)
        }
    }

    fun commit() {
        if (webSocket == null) return
        try {
            // Commit buffer
            val commitEvent = JSONObject()
            commitEvent.put("type", "input_audio_buffer.commit")
            webSocket?.send(commitEvent.toString())

            // Request response
            val createEvent = JSONObject()
            createEvent.put("type", "response.create")
            webSocket?.send(createEvent.toString())
        } catch (e: Exception) {
            Log.e("RealtimeClient", "Error committing", e)
        }
    }

    fun disconnect() {
        webSocket?.close(1000, "User disconnected")
        webSocket = null
    }
}
