package com.example.simultaneous

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.example.simultaneous.ui.MainViewModel
import com.google.android.material.floatingactionbutton.FloatingActionButton

class MainActivity : AppCompatActivity() {

    private val viewModel: MainViewModel by viewModels()

    private val requestPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted: Boolean ->
            if (isGranted) {
                Toast.makeText(this, "Permission granted. Press and hold to speak.", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "Microphone permission is required", Toast.LENGTH_SHORT).show()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val tvStatus = findViewById<TextView>(R.id.tvStatus)
        val tvTranscript = findViewById<TextView>(R.id.tvTranscript)
        val tvTranslation = findViewById<TextView>(R.id.tvTranslation)
        val fabAction = findViewById<FloatingActionButton>(R.id.fabAction)
        val fabSettings = findViewById<FloatingActionButton>(R.id.fabSettings)

        // Observe ViewModel
        viewModel.status.observe(this) { status ->
            tvStatus.text = status
            if (status == "Disconnected" || status.startsWith("Error")) {
                fabAction.setImageResource(android.R.drawable.ic_btn_speak_now)
                fabSettings.isEnabled = true
            } else {
                fabAction.setImageResource(android.R.drawable.ic_media_pause)
                fabSettings.isEnabled = false // Disable settings while running
            }
        }

        viewModel.transcript.observe(this) { text ->
            tvTranscript.text = text
        }

        viewModel.translation.observe(this) { text ->
            tvTranslation.text = text
        }

        // Click Listener replaced by Touch Listener
        fabAction.setOnTouchListener { _, event ->
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                when (event.action) {
                    android.view.MotionEvent.ACTION_DOWN -> {
                        viewModel.startRecording()
                        true
                    }
                    android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                        viewModel.stopRecording()
                        true
                    }
                    else -> false
                }
            } else {
                if (event.action == android.view.MotionEvent.ACTION_DOWN) {
                    requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                }
                true
            }
        }
        
        fabSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
    }
}
