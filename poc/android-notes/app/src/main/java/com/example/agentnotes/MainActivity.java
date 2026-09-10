package com.example.agentnotes;

import android.app.Activity;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.content.SharedPreferences;

public class MainActivity extends Activity {
    private static final String PREFS_NAME = "agent_notes";
    private static final String NOTE_KEY = "note";
    private EditText input;
    private TextView savedNote;
    private SharedPreferences preferences;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        preferences = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 32, 32, 32);

        TextView title = new TextView(this);
        title.setText("Agent Notes");
        title.setTextSize(24);
        root.addView(title, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        input = new EditText(this);
        input.setHint("Write a note...");
        input.setGravity(android.view.Gravity.TOP);
        input.setMinLines(6);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        root.addView(input, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);

        Button save = new Button(this);
        save.setText("Save");
        buttons.addView(save, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1));

        Button clear = new Button(this);
        clear.setText("Clear");
        buttons.addView(clear, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1));

        root.addView(buttons);

        TextView label = new TextView(this);
        label.setText("Currently saved note:");
        label.setTextSize(18);
        root.addView(label);

        savedNote = new TextView(this);
        savedNote.setTextSize(16);
        savedNote.setPadding(0, 12, 0, 0);
        root.addView(savedNote, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        String existingNote = preferences.getString(NOTE_KEY, "");
        savedNote.setText(existingNote.isEmpty() ? "No note saved." : existingNote);
        input.setText(existingNote);

        save.setOnClickListener(v -> {
            String note = input.getText().toString();
            preferences.edit().putString(NOTE_KEY, note).apply();
            savedNote.setText(note.isEmpty() ? "No note saved." : note);
        });

        clear.setOnClickListener(v -> {
            preferences.edit().remove(NOTE_KEY).apply();
            input.setText("");
            savedNote.setText("No note saved.");
        });

        setContentView(root);
    }
}