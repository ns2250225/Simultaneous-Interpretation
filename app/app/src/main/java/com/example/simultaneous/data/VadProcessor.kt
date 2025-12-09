package com.example.simultaneous.data

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

class VadProcessor {

    // Configuration (can be updated)
    var threshold: Int = 500
    var silenceDurationMs: Long = 600
    var minSpeechDurationMs: Long = 300

    // State
    private var isSpeaking = false
    private var lastVoiceTimeNs: Long = 0
    private var segmentStartTimeNs: Long = 0

    enum class VadAction {
        NONE,
        START_SPEAKING,
        COMMIT
    }

    fun reset() {
        isSpeaking = false
        lastVoiceTimeNs = 0
        segmentStartTimeNs = 0
    }

    fun process(pcmData: ByteArray): VadAction {
        // Convert to Shorts to calculate amplitude
        val shorts = ShortArray(pcmData.size / 2)
        ByteBuffer.wrap(pcmData).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().get(shorts)

        var peak = 0
        for (sample in shorts) {
            val absSample = abs(sample.toInt())
            if (absSample > peak) {
                peak = absSample
            }
        }

        val nowNs = System.nanoTime()
        
        // Logic match Python:
        // if peak >= threshold:
        //    last_voice = now
        //    if not speaking: speaking = True; seg_start = now
        // elif speaking and (now - last_voice) >= silence_ms and (now - seg_start) >= min_speech_ms:
        //    speaking = False
        //    return COMMIT

        if (peak >= threshold) {
            lastVoiceTimeNs = nowNs
            if (!isSpeaking) {
                isSpeaking = true
                segmentStartTimeNs = nowNs
                return VadAction.START_SPEAKING
            }
        } else {
            if (isSpeaking) {
                val silenceMs = (nowNs - lastVoiceTimeNs) / 1_000_000
                val speechMs = (nowNs - segmentStartTimeNs) / 1_000_000
                
                if (silenceMs >= silenceDurationMs && speechMs >= minSpeechDurationMs) {
                    isSpeaking = false
                    return VadAction.COMMIT
                }
            }
        }
        return VadAction.NONE
    }
    
    fun isSpeaking(): Boolean = isSpeaking
}
