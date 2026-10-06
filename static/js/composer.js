/* Composer — text, attachments with real upload progress, voice recording.
   Depends on api.js, ui.js. */

const IMAGE_MAX_BYTES = 10 * 1024 * 1024;   // mirrors MediaService limits
const VOICE_MAX_BYTES = 25 * 1024 * 1024;
const REC_MAX_SECONDS = 10 * 60;
const REC_LEVEL_BARS  = 110;   // enough history to span a wide composer; the left edge fades out

// Formats the server accepts (MediaService.ALLOWED_AUDIO_TYPES), best first.
const REC_MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
const AUDIO_EXT = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a', 'audio/mpeg': 'mp3', 'audio/wav': 'wav' };

const _canRecord = () =>
  !!(window.MediaRecorder && navigator.mediaDevices?.getUserMedia && window.isSecureContext);

class Composer {
  /**
   * root — container to render into
   * opts — { roomSlug, roomName, dropTarget, onSendText(content) → bool, onUploaded(message) }
   */
  constructor(root, opts) {
    this.root = root;
    this.opts = opts;
    this.online = false;
    this._upload = null;
    this._rec = null;
    this._dragDepth = 0;
    this._render();
    this._bind();
  }

  _render() {
    this.root.innerHTML = `
      <form class="composer" novalidate>
        <div class="composer-upload" hidden>
          <span class="composer-upload-thumb"></span>
          <span class="composer-upload-info">
            <span class="composer-upload-line">
              <span class="composer-upload-name truncate"></span>
              <span class="composer-upload-pct">0%</span>
            </span>
            <span class="progress" role="progressbar" aria-label="Upload progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
              <span class="progress-bar"></span>
            </span>
          </span>
          <button type="button" class="composer-btn" data-act="cancel-upload" aria-label="Cancel upload">${icon('close', 18)}</button>
        </div>

        <div class="composer-row">
          <input type="file" class="composer-file" accept="image/*,audio/*" hidden>
          <button type="button" class="composer-btn" data-act="attach" aria-label="Attach an image or audio file" title="Attach">${icon('clip', 19)}</button>
          <textarea class="composer-input" rows="1" aria-label="Message" enterkeyhint="send"
                    placeholder="Message ${escHtml(this.opts.roomName)}"></textarea>
          <span class="composer-actions">
            <button type="button" class="composer-btn composer-mic" data-act="record" aria-label="Record a voice note" title="Voice note">${icon('mic', 19)}</button>
            <button type="submit" class="composer-btn composer-send" aria-label="Send message">${icon('arrowUp', 19)}</button>
          </span>
        </div>

        <div class="composer-rec" hidden>
          <button type="button" class="composer-btn" data-act="rec-cancel" aria-label="Discard recording" title="Discard">${icon('trash', 19)}</button>
          <span class="rec-status"><span class="rec-dot" aria-hidden="true"></span><span class="rec-time" role="timer" aria-label="Recording time">0:00</span></span>
          <span class="rec-levels" aria-hidden="true">${'<span></span>'.repeat(REC_LEVEL_BARS)}</span>
          <button type="button" class="composer-btn rec-send" data-act="rec-send" aria-label="Send voice note" title="Send">${icon('arrowUp', 19)}</button>
        </div>
      </form>
      <p class="composer-hint" aria-live="polite"></p>`;

    const q = (s) => this.root.querySelector(s);
    this.el = {
      form:   q('.composer'),
      input:  q('.composer-input'),
      file:   q('.composer-file'),
      send:   q('.composer-send'),
      upload: q('.composer-upload'),
      rec:    q('.composer-rec'),
      hint:   q('.composer-hint'),
      levels: [...this.root.querySelectorAll('.rec-levels span')],
    };
    if (!CSS.supports('field-sizing', 'content')) this._autosize = true;
  }

  _bind() {
    const { form, input, file } = this.el;

    form.addEventListener('submit', (e) => { e.preventDefault(); this._submit(); });

    input.addEventListener('input', () => this._syncText());
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); this._submit(); }
    });
    input.addEventListener('paste', (e) => {
      const f = [...(e.clipboardData?.files || [])].find(x => x.type.startsWith('image/'));
      if (f) { e.preventDefault(); this.sendFile(f); }
    });

    form.addEventListener('click', (e) => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'attach')        file.click();
      if (act === 'record')        this._startRecording();
      if (act === 'rec-cancel')    this._finishRecording(false);
      if (act === 'rec-send')      this._finishRecording(true);
      if (act === 'cancel-upload') this._upload?.abort();
    });

    file.addEventListener('change', () => {
      const f = file.files[0];
      file.value = '';
      if (f) this.sendFile(f);
    });

    form.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this._rec) { e.preventDefault(); e.stopPropagation(); this._finishRecording(false); }
    });

    // Drag a file anywhere over the room to send it
    const t = this.opts.dropTarget;
    if (t) {
      this._onDrag = (e) => {
        if (!e.dataTransfer?.types?.includes('Files')) return;
        e.preventDefault();
        if (e.type === 'dragenter') this._dragDepth++;
        if (e.type === 'dragleave') this._dragDepth--;
        if (e.type === 'drop') {
          this._dragDepth = 0;
          const f = e.dataTransfer.files[0];
          if (f) this.sendFile(f);
        }
        t.classList.toggle('is-dragging', this._dragDepth > 0);
      };
      ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => t.addEventListener(ev, this._onDrag));
    }
  }

  // ── Text ───────────────────────────────────────────────────────────────

  _syncText() {
    const { form, input } = this.el;
    form.classList.toggle('has-text', input.value.trim().length > 0);
    if (this._autosize) {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 200) + 'px';
    }
  }

  _submit() {
    const content = this.el.input.value.trim();
    if (!content) return;
    if (!this.online) {
      this._hint('Not connected yet — your message is still here and will send once you\'re back.');
      return;
    }
    if (this.opts.onSendText(content)) {
      this.el.input.value = '';
      this._syncText();
      this._hint('');
    }
  }

  focus() {
    if (!isTouch()) this.el.input.focus({ preventScroll: true });
  }

  setOnline(on) {
    this.online = on;
    this.el.send.disabled = !on;
    this.el.send.title = on ? '' : 'Waiting for connection';
    if (on) this._hint('');
  }

  _hint(text) { this.el.hint.textContent = text; }

  // ── Attachments ────────────────────────────────────────────────────────

  sendFile(file, { label } = {}) {
    const type = file.type.startsWith('image/') ? 'image'
               : file.type.startsWith('audio/') ? 'voice'
               : null;
    if (!type) { showToast('Only images and audio files can be sent.', 'error'); return; }
    const max = type === 'image' ? IMAGE_MAX_BYTES : VOICE_MAX_BYTES;
    if (file.size > max) {
      showToast(`${type === 'image' ? 'Images' : 'Voice notes'} can be up to ${max / 1024 / 1024} MB.`, 'error');
      return;
    }
    this._send(file, type, label);
  }

  async _send(file, type, label) {
    if (this._upload) { showToast('One upload at a time — hang on a moment.', 'error'); return; }

    const ctrl = new AbortController();
    this._upload = ctrl;
    const { upload } = this.el;
    const thumb = upload.querySelector('.composer-upload-thumb');
    const pct   = upload.querySelector('.composer-upload-pct');
    const bar   = upload.querySelector('.progress');
    let preview = null;

    if (type === 'image') {
      preview = URL.createObjectURL(file);
      thumb.innerHTML = `<img src="${preview}" alt="">`;
    } else {
      thumb.innerHTML = icon('wave', 20);
    }
    upload.querySelector('.composer-upload-name').textContent = label || file.name || (type === 'image' ? 'Image' : 'Voice note');
    const setP = (p) => {
      bar.style.setProperty('--p', p);
      bar.setAttribute('aria-valuenow', String(Math.round(p * 100)));
      pct.textContent = p < 1 ? `${Math.round(p * 100)}%` : 'Sending…';
    };
    setP(0);
    upload.hidden = false;

    const form = new FormData();
    form.append('file', file, file.name || `upload.${type === 'image' ? 'png' : 'webm'}`);
    form.append('message_type', type);

    const res = await apiUpload(`/api/rooms/${this.opts.roomSlug}/upload/`, form, {
      onProgress: setP,
      signal: ctrl.signal,
    });

    if (preview) URL.revokeObjectURL(preview);
    upload.hidden = true;
    this._upload = null;

    if (res.aborted) return;
    if (!res.ok) {
      showToast(res.data?.error || (res.status === 0 ? 'Upload failed — check your connection.' : 'Upload failed.'), 'error');
      return;
    }
    this.opts.onUploaded(res.data);
  }

  // ── Voice recording ────────────────────────────────────────────────────

  async _startRecording() {
    if (this._rec) return;
    if (!_canRecord()) {
      // No recorder here: fall back to picking an audio file.
      this.el.file.accept = 'audio/*';
      this.el.file.click();
      setTimeout(() => { this.el.file.accept = 'image/*,audio/*'; }, 0);
      return;
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (err) {
      showToast(err?.name === 'NotAllowedError'
        ? 'Microphone access is blocked. Allow it in your browser to record.'
        : 'No microphone found.', 'error');
      return;
    }

    const mime = REC_MIME_TYPES.find(t => MediaRecorder.isTypeSupported(t)) || '';
    let recorder;
    try {
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 48000 } : undefined);
    } catch {
      stream.getTracks().forEach(t => t.stop());
      showToast('Recording isn\'t supported in this browser.', 'error');
      return;
    }

    const rec = { recorder, stream, chunks: [], started: performance.now(), mime, raf: 0, timer: 0, ctx: null };
    recorder.ondataavailable = (e) => { if (e.data.size) rec.chunks.push(e.data); };
    recorder.start(250);
    this._rec = rec;

    // Live input level, from the local mic stream
    try {
      rec.ctx = new AudioContext();
      const analyser = rec.ctx.createAnalyser();
      analyser.fftSize = 1024;
      rec.ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      const levels = new Array(REC_LEVEL_BARS).fill(0.06);
      let lastPush = 0;
      const tick = (now) => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
        const level = Math.min(1, Math.sqrt(sum / buf.length) * 4.2);
        if (now - lastPush > 70) {
          levels.shift();
          levels.push(Math.max(0.06, level));
          this.el.levels.forEach((s, i) => { s.style.transform = `scaleY(${levels[i].toFixed(3)})`; });
          lastPush = now;
        }
        rec.raf = requestAnimationFrame(tick);
      };
      rec.raf = requestAnimationFrame(tick);
    } catch { /* meter is decoration; recording still works */ }

    const timeEl = this.root.querySelector('.rec-time');
    rec.timer = setInterval(() => {
      const s = (performance.now() - rec.started) / 1000;
      timeEl.textContent = formatDuration(s);
      if (s >= REC_MAX_SECONDS) this._finishRecording(true);
    }, 250);

    this.el.form.classList.add('is-recording');
    this.el.rec.hidden = false;
    this.root.querySelector('[data-act="rec-send"]').focus();
    announce('Recording started');
  }

  async _finishRecording(send) {
    const rec = this._rec;
    if (!rec) return;
    this._rec = null;

    cancelAnimationFrame(rec.raf);
    clearInterval(rec.timer);
    const stopped = new Promise((res) => { rec.recorder.onstop = res; });
    if (rec.recorder.state !== 'inactive') rec.recorder.stop();
    await stopped;
    rec.stream.getTracks().forEach(t => t.stop());
    rec.ctx?.close().catch(() => {});

    this.el.form.classList.remove('is-recording');
    this.el.rec.hidden = true;
    this.root.querySelector('.rec-time').textContent = '0:00';
    this.el.levels.forEach(s => { s.style.transform = ''; });

    if (!send) { announce('Recording discarded'); this.focus(); return; }

    const seconds = (performance.now() - rec.started) / 1000;
    if (seconds < 0.8 || !rec.chunks.length) { showToast('That was too short to send.', 'error'); return; }

    const type = (rec.recorder.mimeType || rec.mime || 'audio/webm').split(';')[0];
    const file = new File(rec.chunks, `voice-note-${Date.now()}.${AUDIO_EXT[type] || 'webm'}`, { type });
    this.sendFile(file, { label: `Voice note · ${formatDuration(seconds)}` });
    this.focus();
  }

  destroy() {
    this._upload?.abort();
    if (this._rec) {
      const rec = this._rec;
      this._rec = null;
      cancelAnimationFrame(rec.raf);
      clearInterval(rec.timer);
      try { rec.recorder.stop(); } catch { /* already stopped */ }
      rec.stream.getTracks().forEach(t => t.stop());
      rec.ctx?.close().catch(() => {});
    }
    const t = this.opts.dropTarget;
    if (t && this._onDrag) ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => t.removeEventListener(ev, this._onDrag));
  }
}
