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

import android.widget.Switch
import android.widget.ScrollView

class MainActivity : AppCompatActivity() {

    private val viewModel: MainViewModel by viewModels()
    private lateinit var swConnection: Switch
    private lateinit var scrollLog: ScrollView

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
        swConnection = findViewById<Switch>(R.id.swConnection)
        scrollLog = findViewById<ScrollView>(R.id.scrollLog)
        val tvTranscript = findViewById<TextView>(R.id.tvTranscript)
        val tvTranslation = findViewById<TextView>(R.id.tvTranslation)
        val fabAction = findViewById<FloatingActionButton>(R.id.fabAction)
        val fabSettings = findViewById<FloatingActionButton>(R.id.fabSettings)

        // Observe ViewModel
        viewModel.status.observe(this) { status ->
            tvStatus.text = status
            if (status == "已断开" || status.startsWith("错误") || status.startsWith("请先")) {
                fabAction.setImageResource(android.R.drawable.ic_btn_speak_now)
                fabAction.isEnabled = true // Allow pressing even in error state
                fabSettings.isEnabled = true
                if (swConnection.isChecked && (status == "已断开" || status.startsWith("错误"))) {
                     // Do NOT turn off switch automatically unless manually disconnected
                     // swConnection.isChecked = false 
                }
            } else {
                fabAction.isEnabled = true
                if (status == "正在说话...") {
                    fabAction.setImageResource(android.R.drawable.ic_btn_speak_now) // Or mic icon
                } else {
                    fabAction.setImageResource(android.R.drawable.ic_btn_speak_now)
                }
                fabSettings.isEnabled = false // Disable settings while running
            }
        }

        swConnection.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                viewModel.connectSession()
            } else {
                viewModel.stopSession()
            }
        }

        viewModel.transcript.observe(this) { text ->
            tvTranscript.text = text
            scrollLog.post { scrollLog.fullScroll(android.widget.ScrollView.FOCUS_DOWN) }
        }

        viewModel.translation.observe(this) { text ->
            tvTranslation.text = text
            scrollLog.post { scrollLog.fullScroll(android.widget.ScrollView.FOCUS_DOWN) }
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
