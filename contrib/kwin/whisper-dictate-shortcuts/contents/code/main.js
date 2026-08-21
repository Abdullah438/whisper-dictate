function invoke(componentPath) {
    callDBus(
        "org.kde.kglobalaccel",
        componentPath,
        "org.kde.kglobalaccel.Component",
        "invokeShortcut",
        "_launch"
    );
}

function toggleDictation() {
    invoke("/component/local_dictate_toggle_desktop");
}

function rewriteSelection() {
    invoke("/component/local_rewrite_selection_desktop");
}

// Ctrl+? is Shift+/ on a US keyboard. Qt/KWin may report that chord
// as any of these sequences, so register all of them.
registerShortcut("whisper-dictate-toggle-shift-slash", "Whisper Dictation", "Ctrl+Shift+/", toggleDictation);
registerShortcut("whisper-dictate-toggle-question", "Whisper Dictation (Ctrl+?)", "Ctrl+?", toggleDictation);
registerShortcut("whisper-dictate-toggle-slash", "Whisper Dictation (Ctrl+/)", "Ctrl+/", toggleDictation);
registerShortcut("whisper-dictate-toggle-shift-question", "Whisper Dictation (Ctrl+Shift+?)", "Ctrl+Shift+?", toggleDictation);

registerShortcut("whisper-dictate-rewrite", "Rewrite Selection", "Meta+Alt+R", rewriteSelection);
