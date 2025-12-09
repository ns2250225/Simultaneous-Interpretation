package com.example.simultaneous

import android.content.Context
import android.os.Bundle
import android.widget.Button
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.textfield.TextInputEditText

class SettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val prefs = getSharedPreferences("app_settings", Context.MODE_PRIVATE)

        val etApiKey = findViewById<TextInputEditText>(R.id.etApiKey)
        val etBaseUrl = findViewById<TextInputEditText>(R.id.etBaseUrl)
        val etModelName = findViewById<TextInputEditText>(R.id.etModelName)
        val etTargetLanguage = findViewById<TextInputEditText>(R.id.etTargetLanguage)
        
        val seekBarThreshold = findViewById<SeekBar>(R.id.seekBarThreshold)
        val tvThresholdValue = findViewById<TextView>(R.id.tvThresholdValue)
        
        val seekBarSilence = findViewById<SeekBar>(R.id.seekBarSilence)
        val tvSilenceValue = findViewById<TextView>(R.id.tvSilenceValue)
        
        val btnSave = findViewById<Button>(R.id.btnSave)

        // Load current values
        etApiKey.setText(prefs.getString("api_key", "sk-7zp54GI1xp4alaQuydzcxMLhZW47jJAcIJSJksEo7Vfp18Rd"))
        etBaseUrl.setText(prefs.getString("base_url", "ws://jeniya.top"))
        etModelName.setText(prefs.getString("model_name", "gpt-4o-realtime-preview"))
        etTargetLanguage.setText(prefs.getString("target_language", "English"))
        
        val currentThreshold = prefs.getInt("vad_threshold", 500)
        seekBarThreshold.progress = currentThreshold
        tvThresholdValue.text = currentThreshold.toString()

        val currentSilence = prefs.getInt("vad_silence_ms", 600)
        seekBarSilence.progress = currentSilence
        tvSilenceValue.text = "$currentSilence ms"

        // Listeners
        seekBarThreshold.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvThresholdValue.text = progress.toString()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        seekBarSilence.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvSilenceValue.text = "$progress ms"
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        btnSave.setOnClickListener {
            prefs.edit()
                .putString("api_key", etApiKey.text.toString())
                .putString("base_url", etBaseUrl.text.toString())
                .putString("model_name", etModelName.text.toString())
                .putString("target_language", etTargetLanguage.text.toString())
                .putInt("vad_threshold", seekBarThreshold.progress)
                .putInt("vad_silence_ms", seekBarSilence.progress)
                .apply()
            
            finish()
        }
    }
}
