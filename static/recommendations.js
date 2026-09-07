(() => {
    const setText = (id, value) => document.getElementById(id).textContent = value ?? 'Unavailable';
    const configurations = [
        {key: 'crop', url: '/api/crop-recommendation', render(data) {
            setText('recommendedCrop', data.recommended_crop);
            setText('cropWhy', data.explanation.why);
            setText('cropFactors', 'Main factors: ' + data.explanation.main_factors.join('; '));
            setText('cropChange', 'What would change it: ' + data.explanation.what_would_change);
        }},
        {key: 'fertilizer', url: '/api/fertilizer-recommendation', json: true, render(data) {
            setText('recommendedFertilizer', data.recommended_fertilizer);
            setText('fertilizerWhy', data.explanation.why);
            setText('fertilizerFactors', 'Main factors: ' + data.explanation.main_factors.join('; '));
            setText('fertilizerChange', 'What would change it: ' + data.explanation.what_would_change);
        }},
        {key: 'price', url: '/api/crop-price-prediction', render(data) {
            setText('predictedPrice', Number(data.predicted_price).toLocaleString('en-IN', {maximumFractionDigits: 2}));
            setText('priceOutlook', data.outlook);
            setText('priceAction', data.recommended_action);
            setText('priceWhy', data.explanation.why);
            setText('priceChange', 'What would change it: ' + data.explanation.what_would_change);
        }}
    ];
    configurations.forEach(config => {
        const form = document.getElementById(config.key + 'Form');
        const status = document.getElementById(config.key + 'Status');
        const result = document.getElementById(config.key + 'Result');
        const button = form.querySelector('[type="submit"]');
        const label = button.textContent;
        let busy = false;
        let revision = 0;
        form.addEventListener('input', () => {
            revision++;
            result.classList.add('d-none');
            status.textContent = '';
        });
        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (busy || !form.reportValidity()) return;
            busy = true;
            const submittedRevision = revision;
            button.disabled = true;
            button.textContent = 'Checking…';
            form.setAttribute('aria-busy', 'true');
            status.classList.remove('is-error');
            status.textContent = 'Preparing your suggestion…';
            result.classList.add('d-none');
            const fields = new FormData(form);
            const options = {method: 'POST', body: fields};
            if (config.json) {
                const values = Object.fromEntries(fields);
                form.querySelectorAll('[type="number"]').forEach(input => values[input.name] = Number(input.value));
                options.headers = {'Content-Type': 'application/json'};
                options.body = JSON.stringify(values);
            }
            try {
                const data = await Krishi.request(config.url, options);
                if (revision !== submittedRevision) {
                    status.textContent = 'Inputs changed while checking. Submit again for an updated suggestion.';
                    return;
                }
                config.render(data);
                status.textContent = '';
                result.classList.remove('d-none');
                result.focus({preventScroll: true});
                result.scrollIntoView({block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
            } catch (error) {
                status.classList.add('is-error');
                status.textContent = error.message + ' Your inputs are kept. Please try again.';
            } finally {
                busy = false;
                button.disabled = false;
                button.textContent = label;
                form.setAttribute('aria-busy', 'false');
            }
        });
    });

    document.getElementById('sampleInputs').addEventListener('click', () => {
        const values = {nitrogen: 70, phosphorus: 45, potassium: 40, temperature: 28, humidity: 70, ph: 6.6, rainfall: 120};
        for (const [id, value] of Object.entries(values)) document.getElementById(id).value = value;
        document.getElementById('cropForm').dispatchEvent(new Event('input', {bubbles: true}));
        setText('inputMode', 'Sample inputs loaded — replace them with your readings for a field-specific suggestion.');
    });

    const tabs = ['crop', 'fertilizer', 'price', 'disease'];
    function openHash() {
        const id = location.hash.slice(1);
        if (tabs.includes(id)) bootstrap.Tab.getOrCreateInstance(document.getElementById(id + '-tab')).show();
    }
    openHash();
    addEventListener('hashchange', openHash);
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => tab.addEventListener('shown.bs.tab', () => {
        history.replaceState(null, '', '#' + tab.getAttribute('aria-controls'));
    }));
    const currentMonth = new Date().getMonth() + 1;
    document.getElementById('month').value = currentMonth;
})();
