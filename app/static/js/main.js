document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    fetchClients();

    // Poll for status updates every 5 seconds
    setInterval(() => {
        fetchStats();
        fetchClients(true); // silent fetch (no reloading state flickering)
    }, 5000);
});

async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        
        document.getElementById('stat-total').innerText = data.total_clients;
        document.getElementById('stat-active').innerText = data.active_clients;
        
        const assistantText = data.assistant_online ? 'ONLINE' : 'OFFLINE';
        const assistantEl = document.getElementById('stat-assistant');
        assistantEl.innerText = assistantText;
        assistantEl.style.color = data.assistant_online ? 'var(--success)' : 'var(--danger)';
    } catch (err) {
        console.error('Error fetching stats:', err);
    }
}

async function fetchClients(silent = false) {
    const container = document.getElementById('clients-container');
    if (!silent) {
        container.innerHTML = `
            <div class="empty-state">
                <p>Memuat data client...</p>
            </div>
        `;
    }

    try {
        const res = await fetch('/api/clients');
        const clients = await res.json();

        if (clients.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-inbox"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
                    <p>Belum ada client yang terdaftar.<br>Tambahkan melalui Bot Asisten Telegram.</p>
                </div>
            `;
            return;
        }

        let html = '';
        clients.forEach(client => {
            const isOnline = client.status === 'online';
            const statusClass = isOnline ? 'status-online' : 'status-offline';
            const actionBtn = isOnline 
                ? `<button class="btn btn-danger" onclick="toggleClient('${client.phone_number}', 'stop')">Hentikan</button>`
                : `<button class="btn btn-primary" onclick="toggleClient('${client.phone_number}', 'start')">Jalankan</button>`;

            html += `
                <div class="client-item">
                    <div class="client-info">
                        <span class="client-phone">${client.phone_number}</span>
                        <span class="client-date">Ditambahkan: ${new Date(client.created_at).toLocaleDateString('id-ID')}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 1.5rem;">
                        <span class="client-status ${statusClass}">
                            <span class="status-dot" style="background-color: ${isOnline ? 'var(--success)' : 'var(--danger)'}; box-shadow: none; animation: none;"></span>
                            ${client.status}
                        </span>
                        <div class="btn-actions">
                            ${actionBtn}
                            <button class="btn btn-danger" style="background: transparent; border-color: rgba(239,68,68,0.2);" onclick="deleteClient('${client.phone_number}')">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-trash-2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    } catch (err) {
        console.error('Error fetching clients:', err);
        container.innerHTML = `
            <div class="empty-state" style="color: var(--danger)">
                <p>Gagal memuat data client.</p>
            </div>
        `;
    }
}

async function toggleClient(phone, action) {
    try {
        const res = await fetch(`/api/clients/${encodeURIComponent(phone)}/${action}`, {
            method: 'POST'
        });
        const data = await res.json();
        if (data.success) {
            fetchClients(true);
            fetchStats();
        } else {
            alert('Gagal mengubah status client: ' + data.message);
        }
    } catch (err) {
        console.error('Error toggling client:', err);
    }
}

async function deleteClient(phone) {
    if (!confirm(`Apakah Anda yakin ingin menghapus client ${phone}? Sesi akan dihapus secara permanen.`)) {
        return;
    }
    
    try {
        const res = await fetch(`/api/clients/${encodeURIComponent(phone)}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
            fetchClients(true);
            fetchStats();
        } else {
            alert('Gagal menghapus client: ' + data.message);
        }
    } catch (err) {
        console.error('Error deleting client:', err);
    }
}

async function addSession(event) {
    event.preventDefault();
    const phone = document.getElementById('session-phone').value.trim();
    const sessionString = document.getElementById('session-string').value.trim();

    try {
        const res = await fetch('/api/clients/add_session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                phone_number: phone,
                session_string: sessionString
            })
        });
        const data = await res.json();
        if (data.success) {
            alert('Client berhasil ditambahkan!');
            document.getElementById('session-form').reset();
            fetchClients(true);
            fetchStats();
        } else {
            alert('Gagal menambahkan client: ' + data.message);
        }
    } catch (err) {
        console.error('Error adding session:', err);
        alert('Terjadi kesalahan.');
    }
}

