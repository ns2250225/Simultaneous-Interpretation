package com.example.simultaneous.data

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.nio.ByteBuffer
import java.nio.ByteOrder

class AudioEngine {

    companion object {
        const val SAMPLE_RATE = 24000
        const val CHANNEL_CONFIG_IN = AudioFormat.CHANNEL_IN_MONO
        const val CHANNEL_CONFIG_OUT = AudioFormat.CHANNEL_OUT_MONO
        const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        // Python used 1024 samples = 2048 bytes.
        // We want small chunks for low latency.
        const val CHUNK_SIZE_SAMPLES = 1024 
    }

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var isRecording = false
    private var recordJob: Job? = null
    
    // Channel to emit recorded audio chunks
    private val _audioInputChannel = Channel<ByteArray>(Channel.UNLIMITED)
    val audioInputFlow: Flow<ByteArray> = _audioInputChannel.receiveAsFlow()

    @SuppressLint("MissingPermission")
    fun startRecording(scope: CoroutineScope) {
        if (isRecording) return

        val minBufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG_IN, AUDIO_FORMAT)
        val bufferSize = maxOf(minBufferSize, CHUNK_SIZE_SAMPLES * 2)

        Log.d("AudioEngine", "Min Buffer Size: $minBufferSize, Using: $bufferSize")

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                CHANNEL_CONFIG_IN,
                AUDIO_FORMAT,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e("AudioEngine", "AudioRecord initialization failed")
                return
            }

            audioRecord?.startRecording()
            isRecording = true
            Log.d("AudioEngine", "Recording started")

            recordJob = scope.launch(Dispatchers.IO) {
                val buffer = ByteArray(CHUNK_SIZE_SAMPLES * 2) // 1024 samples * 2 bytes
                while (isActive && isRecording) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                    if (read > 0) {
                        // Copy data to emit (safety)
                        val data = buffer.copyOf(read)
                        _audioInputChannel.trySend(data)
                    } else {
                         // Error or end
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("AudioEngine", "Error starting recording", e)
        }
    }

    fun stopRecording() {
        isRecording = false
        try {
            recordJob?.cancel()
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null
            Log.d("AudioEngine", "Recording stopped")
        } catch (e: Exception) {
            Log.e("AudioEngine", "Error stopping recording", e)
        }
    }

    fun initPlayer() {
        if (audioTrack != null) return

        val minBufferSize = AudioTrack.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG_OUT, AUDIO_FORMAT)
        val bufferSize = maxOf(minBufferSize, CHUNK_SIZE_SAMPLES * 2)

        try {
            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AUDIO_FORMAT)
                        .setSampleRate(SAMPLE_RATE)
                        .setChannelMask(CHANNEL_CONFIG_OUT)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            audioTrack?.play()
            Log.d("AudioEngine", "AudioTrack initialized and playing")
        } catch (e: Exception) {
            Log.e("AudioEngine", "Error initializing player", e)
        }
    }

    fun playAudio(pcmData: ByteArray) {
        if (audioTrack == null) initPlayer()
        try {
            audioTrack?.write(pcmData, 0, pcmData.size)
        } catch (e: Exception) {
            Log.e("AudioEngine", "Error writing audio", e)
        }
    }

    fun release() {
        stopRecording()
        audioTrack?.stop()
        audioTrack?.release()
        audioTrack = null
    }
}
