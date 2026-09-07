/* Shared, dependency-free interaction and request handling. */
window.Krishi = (() => {
    const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);

    async function request(url, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 20000);
        try {
            const response = await fetch(url, { credentials: 'same-origin', ...options, signal: controller.signal });
            if (response.status === 401) {
                window.location.assign('/login?next=' + encodeURIComponent(location.pathname + location.hash));
                throw new Error('Your session has expired. Please sign in again.');
            }
            const data = await response.json();
            if (!response.ok) {
                const detail = Array.isArray(data.detail)
                    ? data.detail.map(item => `${item.loc?.at(-1) || 'Input'}: ${item.msg}`).join('. ')
                    : data.detail;
                throw new Error(detail || 'Unable to complete the request. Please try again.');
            }
            return data;
        } catch (error) {
            if (error.name === 'AbortError') throw new Error('This is taking too long. Please try again.');
            if (error instanceof TypeError) throw new Error('Unable to connect. Check your connection and try again.');
            throw error;
        } finally { clearTimeout(timeout); }
    }

    function notice(message, retry) {
        const target = document.getElementById('pageNotice');
        target.hidden = false;
        target.className = 'page-notice is-error';
        target.textContent = message;
        if (retry) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-outline-success';
            button.textContent = 'Try again';
            button.addEventListener('click', () => { target.hidden = true; retry(); });
            target.append(button);
        }
    }

    function loadFailure(error, retry) {
        document.querySelectorAll('#main-content *').forEach(element => {
            if (!element.children.length && /^Loading/.test(element.textContent.trim())) element.textContent = 'Unavailable';
        });
        notice(error.message, retry);
    }

    function bindAssistant({ formId, inputId, logId }) {
        const form = document.getElementById(formId);
        const input = document.getElementById(inputId);
        const log = document.getElementById(logId);
        const buttons = [...form.querySelectorAll('button'), ...form.parentElement.querySelectorAll('.quick-question')];
        let busy = false;
        async function ask(question) {
            question = question.trim();
            if (busy || !question || question.length > 1000) return;
            busy = true;
            buttons.forEach(button => button.disabled = true);
            log.setAttribute('aria-busy', 'true');
            const user = document.createElement('div');
            user.className = 'assistant-message';
            user.textContent = 'You: ' + question;
            const answer = document.createElement('div');
            answer.className = 'assistant-message';
            answer.textContent = 'Reviewing your decision card…';
            log.append(user, answer);
            log.scrollTop = log.scrollHeight;
            try {
                const result = await request('/api/assistant', {
                    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question})
                });
                answer.textContent = `${result.answer}\n\nRecommended action: ${result.recommended_action}\nData used: ${(result.data_used || []).join('; ')}\nConfidence: ${result.confidence}\nLimitation: ${(result.limitations || []).join('; ')}`;
                if (input.value.trim() === question) input.value = '';
            } catch (error) {
                answer.classList.add('text-danger');
                answer.textContent = error.message + ' Your question is kept below.';
                if (!input.value.trim()) input.value = question;
            } finally {
                busy = false;
                buttons.forEach(button => button.disabled = false);
                log.setAttribute('aria-busy', 'false');
                log.scrollTop = log.scrollHeight;
            }
        }
        form.addEventListener('submit', event => { event.preventDefault(); if (form.reportValidity()) ask(input.value); });
        return ask;
    }

    const nav = document.getElementById('app-navigation');
    const toggles = [...document.querySelectorAll('.menu-toggle')];
    let opener;
    function setMenu(open, focus = false) {
        nav.classList.toggle('is-open', open);
        toggles.forEach(button => button.setAttribute('aria-expanded', String(open)));
        if (open && focus) nav.querySelector('a').focus();
        if (!open && focus) opener?.focus();
    }
    toggles.forEach(button => button.addEventListener('click', () => {
        opener = button;
        setMenu(!nav.classList.contains('is-open'), true);
    }));
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && nav.classList.contains('is-open')) setMenu(false, true);
    });
    document.addEventListener('click', event => {
        if (!nav.contains(event.target) && !event.target.closest('.menu-toggle')) setMenu(false);
    });
    nav.addEventListener('click', event => { if (event.target.closest('a')) setMenu(false); });
    document.addEventListener('focusin', event => {
        if (!nav.contains(event.target) && !event.target.closest('.menu-toggle')) setMenu(false);
    });
    matchMedia('(min-width: 992px)').addEventListener('change', () => setMenu(false));
    document.querySelectorAll('i.bi').forEach(icon => icon.setAttribute('aria-hidden', 'true'));
    document.querySelectorAll('.table-responsive').forEach(table => {
        table.tabIndex = 0;
        table.setAttribute('role', 'region');
        table.setAttribute('aria-label', 'Sensor readings; scroll horizontally for more columns');
    });
    document.getElementById('signOut')?.addEventListener('click', async event => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
            const {csrf_token} = await request('/api/auth/csrf');
            await request('/api/auth/logout', {method: 'POST', headers: {'X-CSRF-Token': csrf_token}});
            location.assign('/login');
        } catch (error) { notice(error.message); button.disabled = false; }
    });
    return {request, escapeHTML, notice, loadFailure, bindAssistant};
})();
