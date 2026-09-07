(() => {
    const definitions = [
        ['temperatureChart', 'field1', 'Temperature'], ['humidityChart', 'field2', 'Humidity'],
        ['moistureChart', 'field3', 'Soil moisture'], ['lightChart', 'field4', 'Light intensity'],
        ['pumpChart', 'field5', 'Pump']
    ];
    const number = value => value === null || value === '' || value === undefined || !Number.isFinite(Number(value)) ? null : Number(value);
    const pump = value => value === 'on' ? 1 : value === 'off' ? 0 : null;
    const charts = definitions.map(([id, field, label]) => new Chart(document.getElementById(id), {
        type: 'line',
        data: {datasets: [{label, data: [], borderColor: '#246b4e', backgroundColor: '#246b4e', borderWidth: 2, pointRadius: 3, spanGaps: false, stepped: field === 'field5'}]},
        options: {
            responsive: true, maintainAspectRatio: false, animation: false,
            plugins: {legend: {display: false}, tooltip: {callbacks: {title: items => new Date(items[0].parsed.x).toLocaleString()}}},
            scales: {
                x: {type: 'linear', ticks: {maxTicksLimit: 4, callback: value => new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}},
                y: field === 'field5' ? {min: 0, max: 1, ticks: {stepSize: 1, callback: value => value ? 'On' : 'Off'}} : {}
            }
        }
    }));
    const status = document.getElementById('sensorStatus');
    const button = document.getElementById('refreshSensors');
    const table = document.getElementById('sensorDataTable');
    let busy = false;
    let timer;

    function render(feeds, alerts) {
        const rows = feeds.filter(row => Number.isFinite(Date.parse(row.created_at))).sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at)).slice(-10);
        definitions.forEach(([, field], index) => {
            charts[index].data.datasets[0].data = rows.map(row => ({x: Date.parse(row.created_at), y: field === 'field5' ? pump(row[field]) : number(row[field])}));
            charts[index].update('none');
        });
        table.replaceChildren();
        rows.slice().reverse().forEach(row => {
            const tr = document.createElement('tr');
            const values = [new Date(row.created_at).toLocaleString(), ...['field1', 'field2', 'field3', 'field4'].map(field => number(row[field])?.toFixed(1) ?? '—'), pump(row.field5) === null ? '—' : pump(row.field5) ? 'On' : 'Off'];
            values.forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
            table.append(tr);
        });
        if (!rows.length) {
            const tr = table.insertRow();
            const td = tr.insertCell(); td.colSpan = 6; td.textContent = 'No readings available. Check the sensor connection and try refreshing.';
        }
        const target = document.getElementById('iotAlerts');
        target.replaceChildren();
        alerts.forEach(alert => {
            const item = document.createElement('div');
            item.className = 'col-md-6';
            const strong = document.createElement('strong');
            strong.textContent = `${alert.severity}: ${alert.message}`;
            const detail = document.createElement('p'); detail.className = 'small text-muted mb-0'; detail.textContent = alert.recommended_action;
            item.append(strong, detail); target.append(item);
        });
        if (!alerts.length) target.textContent = rows.length ? 'No threshold alerts in the latest snapshot.' : 'Alerts need available sensor readings.';
        return rows;
    }
    async function refresh() {
        if (busy || document.hidden) return;
        clearTimeout(timer);
        busy = true; button.disabled = true; button.textContent = 'Refreshing…';
        status.textContent = 'Checking for readings…';
        try {
            const data = await Krishi.request('/api/data');
            const rows = render(data.feeds || [], data.anomalies?.alerts || []);
            if (rows.length) {
                const latest = new Date(rows.at(-1).created_at);
                const stale = Date.now() - latest.getTime() > 30 * 60000;
                status.textContent = `${stale ? 'Older readings — ' : ''}Last reading: ${latest.toLocaleString()}. Checks every 15 seconds while this page is visible.`;
            } else status.textContent = 'No sensor readings available. Check your configured channel, then refresh.';
        } catch (error) {
            render([], []);
            status.textContent = error.message + ' Use Refresh to retry.';
        } finally {
            busy = false; button.disabled = false; button.textContent = 'Refresh';
            if (!document.hidden) timer = setTimeout(refresh, 15000);
        }
    }
    button.addEventListener('click', refresh);
    document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) refresh(); });
    window.addEventListener('pagehide', () => clearTimeout(timer));
    window.addEventListener('pageshow', event => { if (event.persisted) refresh(); });
    refresh();
})();
