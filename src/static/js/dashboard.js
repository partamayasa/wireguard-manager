    let allPeers = [];
    let currentConfigText = '';
    let currentDnsPresets = [];
    let currentServerStatus = {};

    function showToast(msg, isError = false) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.style.borderColor = isError ? 'var(--danger)' : 'var(--primary)';
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3500);
    }

    async function checkAuth() {
      try {
        const res = await fetch('/api/check-auth');
        const data = await res.json();
        const loginEl = document.getElementById('login-view');
        const dashEl = document.getElementById('dashboard-view');
        if (data.authenticated) {
          loginEl.classList.add('d-none');
          loginEl.style.display = 'none';
          dashEl.classList.remove('d-none');
          dashEl.style.display = '';
          if (typeof window.initSidebarScrollbars === 'function') {
            window.initSidebarScrollbars();
          }
          loadData();
          loadDnsPresets();
        } else {
          loginEl.classList.remove('d-none');
          loginEl.style.display = 'flex';
          dashEl.classList.add('d-none');
          dashEl.style.display = 'none';
        }
      } catch (e) {
        document.getElementById('login-view').classList.remove('d-none');
        document.getElementById('login-view').style.display = 'flex';
        document.getElementById('dashboard-view').classList.add('d-none');
        document.getElementById('dashboard-view').style.display = 'none';
      }
    }

    async function handleLogin(e) {
      e.preventDefault();
      const usernameInput = document.getElementById('login-username');
      const passwordInput = document.getElementById('login-password');
      const username = usernameInput ? usernameInput.value.trim() : 'admin';
      const password = passwordInput ? passwordInput.value : '';
      const btn = document.getElementById('btn-login');
      if (btn) btn.disabled = true;
      try {
        const res = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: username, password: password })
        });
        const data = await res.json();
        if (res.ok) {
          checkAuth();
        } else {
          showToast(data.error || 'Login failed', true);
        }
      } catch (err) {
        showToast('Network error during login', true);
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    async function handleLogout() {
      await fetch('/api/logout', { method: 'POST' });
      checkAuth();
    }

    async function loadData() {
      await Promise.all([loadStatus(), loadPeers()]);
    }

    async function loadStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const s = await res.json();
        currentServerStatus = s;
        const badge = document.getElementById('stat-status');
        if (s.active) {
          badge.className = 'badge text-bg-success px-2 py-1';
          badge.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Active';
        } else {
          badge.className = 'badge text-bg-danger px-2 py-1';
          badge.innerHTML = '<i class="bi bi-x-circle-fill me-1"></i> Inactive';
        }
        document.getElementById('stat-endpoint').innerText = (s.endpoint ? s.endpoint + ':' : '') + (s.listen_port || '-');
        document.getElementById('stat-peers').innerHTML = `${s.peer_count} <span style="font-size: 1rem; color: #34d399; font-weight: 500;">/ ${s.online_peers} Online</span>`;
        document.getElementById('stat-subnet').innerText = s.subnet || '-';
        document.getElementById('stat-rx').innerText = s.total_rx;
        document.getElementById('stat-tx').innerText = s.total_tx;
      } catch (e) {}
    }

    async function loadPeers() {
      try {
        const res = await fetch('/api/peers');
        if (!res.ok) return;
        const data = await res.json();
        allPeers = data.peers || [];
        renderPeers(allPeers);
      } catch (e) {}
    }

    function renderPeers(peers) {
      const tbody = document.getElementById('peer-table-body');
      const countEl = document.getElementById('client-table-count');
      if (countEl) {
        countEl.innerText = `Showing ${peers.length} of ${allPeers.length} clients`;
      }
      if (peers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">No registered clients found.</td></tr>';
        return;
      }
      tbody.innerHTML = peers.map(p => `
        <tr>
          <td class="text-center" style="width: 1%; white-space: nowrap;">
            <span class="badge ${p.is_online ? 'text-bg-success' : 'text-bg-secondary'} px-2 py-1 fw-normal">
              <i class="bi ${p.is_online ? 'bi-check-circle-fill' : 'bi-dash-circle'} me-1"></i> ${p.is_online ? 'Active' : 'Offline'}
            </span>
          </td>
          <td class="text-center align-middle">
            <div class="peer-name">
              <i class="bi bi-display text-primary me-2 fs-6"></i>
              <span>${p.name}</span>
            </div>
          </td>
          <td class="text-center align-middle"><span class="font-monospace text-primary fw-normal">${p.ip_address || p.allowed_ips}</span></td>
          <td class="text-center align-middle"><span class="text-secondary small fw-normal">${p.latest_handshake}</span></td>
          <td class="text-center align-middle"><span class="text-primary fw-normal">↓ ${p.rx}</span> / <span class="text-warning fw-normal">↑ ${p.tx}</span></td>
          <td class="text-center" style="width: 290px; min-width: 290px; white-space: nowrap;">
            <div class="action-group">
              <button class="btn btn-outline-primary action-btn" onclick="showQrModal('${p.name}')"><i class="bi bi-qr-code"></i><span>QR&nbsp;/&nbsp;Config</span></button>
              <button class="btn btn-outline-secondary action-btn" onclick="openPeerSettingsModal('${p.name}', '${p.client_allowed_ips || '0.0.0.0/0, ::/0'}')"><i class="bi bi-gear"></i><span>Setting</span></button>
              <button class="btn btn-outline-danger action-btn" onclick="confirmDeletePeer('${p.name}')"><i class="bi bi-trash"></i><span>Delete</span></button>
            </div>
          </td>
        </tr>
      `).join('');
    }

    function filterPeers() {
      const input = document.getElementById('table-filter') || document.getElementById('search-peer');
      const q = input ? input.value.toLowerCase() : '';
      const filtered = allPeers.filter(p => (p.name || '').toLowerCase().includes(q) || (p.allowed_ips || '').toLowerCase().includes(q));
      renderPeers(filtered);
    }

    function exportPeersCsv() {
      if (!allPeers || allPeers.length === 0) {
        showToast('No clients to export', true);
        return;
      }
      const headers = ['Name', 'IP Address', 'Public Key', 'Status', 'Latest Handshake', 'RX', 'TX'];
      const rows = allPeers.map(p => [
        `"${p.name || ''}"`,
        `"${p.allowed_ips || ''}"`,
        `"${p.public_key || ''}"`,
        `"${p.is_online ? 'Active' : 'Offline'}"`,
        `"${p.latest_handshake || '-'}"`,
        `"${p.rx || '0 B'}"`,
        `"${p.tx || '0 B'}"`
      ]);
      const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement('a');
      link.setAttribute('href', encodedUri);
      link.setAttribute('download', 'wireguard_users.csv');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast('Exported users to CSV successfully');
    }

    function exportPeersJson() {
      if (!allPeers || allPeers.length === 0) {
        showToast('No clients to export', true);
        return;
      }
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(allPeers, null, 2));
      const link = document.createElement('a');
      link.setAttribute('href', dataStr);
      link.setAttribute('download', 'wireguard_users.json');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast('Exported users to JSON successfully');
    }

    async function loadDnsPresets() {
      try {
        const res = await fetch('/api/dns-presets');
        if (!res.ok) return;
        const data = await res.json();
        currentDnsPresets = data.presets || [];
        populateDnsDropdown();
        renderDnsPresetsList();
      } catch (e) {}
    }

    function populateDnsDropdown() {
      const select = document.getElementById('add-dns');
      if (!select) return;
      if (!currentDnsPresets || currentDnsPresets.length === 0) {
        select.innerHTML = '<option value="1.1.1.1, 1.0.0.1">Cloudflare (1.1.1.1, 1.0.0.1)</option>';
        return;
      }
      select.innerHTML = currentDnsPresets.map(p => `
        <option value="${p.value}">${p.name} (${p.value})</option>
      `).join('');
    }

    function renderDnsPresetsList() {
      const container = document.getElementById('dns-presets-list');
      if (!container) return;
      container.innerHTML = currentDnsPresets.map(p => `
        <div class="d-flex justify-content-between align-items-center p-2 mb-2 bg-body-tertiary border rounded">
          <div>
            <div class="fw-bold text-body" style="font-size: 0.9rem;">${p.name}</div>
            <div class="font-monospace text-primary small">${p.value}</div>
          </div>
          <div>
            ${p.is_default ? '<span class="badge text-bg-secondary">Default</span>' : `<button class="btn btn-sm btn-outline-danger" onclick="handleDeleteDnsPreset('${p.id}')"><i class="bi bi-trash me-1"></i> Delete</button>`}
          </div>
        </div>
      `).join('');
    }

    function openAddModal() {
      document.getElementById('add-name').value = '';
      populateDnsDropdown();
      document.getElementById('add-modal').style.display = 'flex';
      setTimeout(() => {
        const input = document.getElementById('add-name');
        if (input) input.focus();
      }, 50);
    }

    function openServerSettingsModal() {
      document.getElementById('settings-endpoint').value = currentServerStatus.endpoint || '';
      document.getElementById('settings-port').value = currentServerStatus.listen_port || '51820';
      document.getElementById('settings-update-clients').checked = true;
      document.getElementById('server-settings-modal').style.display = 'flex';
    }

    async function detectPublicIP() {
      const btn = document.getElementById('btn-detect-ip');
      const input = document.getElementById('settings-endpoint');
      if (!btn) return;
      const originalHTML = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Detecting...';

      try {
        const res = await fetch('/api/detect-ip');
        const data = await res.json();
        if (res.ok && data.success && data.ip) {
          if (input) {
            input.value = data.ip;
            input.focus();
          }
          showToast('Server public IP detected: ' + data.ip);
        } else {
          showToast(data.error || 'Failed to detect server public IP', true);
        }
      } catch (err) {
        showToast('Network error while detecting server public IP', true);
      } finally {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
      }
    }

    async function handleSaveServerSettings(e) {
      e.preventDefault();
      const endpoint = document.getElementById('settings-endpoint').value.trim();
      const port = document.getElementById('settings-port').value.trim();
      const updateClients = document.getElementById('settings-update-clients').checked;

      const res = await fetch('/api/server-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: endpoint,
          port: port,
          update_clients: updateClients
        })
      });
      const data = await res.json();
      if (res.ok) {
        closeModal('server-settings-modal');
        showToast(data.message);
        loadData();
      } else {
        showToast(data.error || 'Failed to update server settings', true);
      }
    }

    function openDnsModal() {
      renderDnsPresetsList();
      document.getElementById('dns-modal').style.display = 'flex';
    }

    async function openAuditLogsModal() {
      const container = document.getElementById('audit-logs-list');
      container.innerHTML = '<div class="text-secondary text-center py-4">Loading logs...</div>';
      document.getElementById('logs-modal').style.display = 'flex';

      try {
        const res = await fetch('/api/audit-logs');
        const data = await res.json();
        if (data.logs && data.logs.length > 0) {
          container.innerHTML = data.logs.map(log => `
            <div class="p-2 mb-2 bg-body-tertiary border rounded small">
              <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="badge text-bg-primary">${log.action}</span>
                <span class="text-secondary" style="font-size: 0.75rem;">${log.timestamp}</span>
              </div>
              <div class="text-body">${log.detail}</div>
            </div>
          `).join('');
        } else {
          container.innerHTML = '<div class="text-secondary text-center py-4">No logs recorded yet.</div>';
        }
      } catch (e) {
        container.innerHTML = '<div class="text-danger text-center py-4">Failed to load logs.</div>';
      }
    }

    function closeModal(id) {
      document.getElementById(id).style.display = 'none';
    }

    async function handleAddPeer(e) {
      e.preventDefault();
      const name = document.getElementById('add-name').value.trim();
      const dns = document.getElementById('add-dns').value || '1.1.1.1, 1.0.0.1';

      const res = await fetch('/api/peers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name,
          dns: dns
        })
      });
      const data = await res.json();
      if (res.ok) {
        closeModal('add-modal');
        showToast(data.message);
        loadData();
        showQrModal(name);
      } else {
        showToast(data.error || 'Failed to add client', true);
      }
    }

    async function handleCreateDnsPreset(e) {
      e.preventDefault();
      const name = document.getElementById('new-dns-name').value.trim();
      const val = document.getElementById('new-dns-value').value.trim();
      const res = await fetch('/api/dns-presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, value: val })
      });
      const data = await res.json();
      if (res.ok) {
        document.getElementById('new-dns-name').value = '';
        document.getElementById('new-dns-value').value = '';
        showToast(data.message);
        loadDnsPresets();
      } else {
        showToast(data.error || 'Failed to add DNS preset', true);
      }
    }

    async function handleDeleteDnsPreset(presetId) {
      if (!confirm('Are you sure you want to remove this DNS preset?')) return;
      const res = await fetch('/api/dns-presets/' + presetId, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message);
        loadDnsPresets();
      } else {
        showToast(data.error || 'Failed to delete preset', true);
      }
    }

    async function confirmDeletePeer(name) {
      if (!confirm(`Are you sure you want to delete client "${name}"?`)) return;
      const res = await fetch('/api/peers/' + name, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message);
        loadData();
      } else {
        showToast(data.error || 'Failed to delete client', true);
      }
    }

    function openPeerSettingsModal(name, allowedIps) {
      document.getElementById('peer-settings-title').innerText = 'Client Settings: ' + name;
      document.getElementById('edit-peer-name').value = name;
      document.getElementById('edit-peer-allowed-ips').value = allowedIps || '';
      document.getElementById('peer-settings-modal').style.display = 'flex';
      setTimeout(() => {
        const input = document.getElementById('edit-peer-allowed-ips');
        if (input) input.focus();
      }, 50);
    }

    async function handleSavePeerSettings(e) {
      e.preventDefault();
      const name = document.getElementById('edit-peer-name').value;
      const allowedIps = document.getElementById('edit-peer-allowed-ips').value.trim();

      if (!allowedIps) {
        showToast('AllowedIPs cannot be empty', true);
        return;
      }

      const res = await fetch('/api/peers/' + encodeURIComponent(name) + '/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ allowed_ips: allowedIps })
      });
      const data = await res.json();
      if (res.ok) {
        closeModal('peer-settings-modal');
        showToast(data.message || 'AllowedIPs updated successfully');
        loadData();
      } else {
        showToast(data.error || 'Failed to update AllowedIPs', true);
      }
    }

    function downloadConfigFile(name, content) {
      if (!content) {
        window.location.href = '/api/peers/' + encodeURIComponent(name) + '/download';
        return;
      }
      try {
        const blob = new Blob([content], { type: 'application/octet-stream' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = name + '.conf';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }, 1000);
      } catch (e) {
        window.location.href = '/api/peers/' + encodeURIComponent(name) + '/download';
      }
    }

    async function downloadPeerConfig(name) {
      try {
        const res = await fetch('/api/peers/' + encodeURIComponent(name) + '/config');
        if (res.ok) {
          let text = await res.text();
          try {
            const parsed = JSON.parse(text);
            if (parsed && typeof parsed === 'object') {
              if (parsed.config) text = parsed.config;
              else if (parsed.content) text = parsed.content;
            }
          } catch(e) {}
          downloadConfigFile(name, text.trim());
          return;
        }
      } catch (err) {}
      window.location.href = '/api/peers/' + encodeURIComponent(name) + '/download';
    }

    async function showQrModal(name) {
      document.getElementById('qr-modal-title').innerText = 'Client: ' + name;
      const box = document.getElementById('qr-box');
      const preview = document.getElementById('conf-preview');
      currentConfigText = '';
      box.innerHTML = '<div class="d-flex align-items-center justify-content-center text-secondary py-4"><div class="spinner-border spinner-border-sm me-2"></div> Loading QR...</div>';
      preview.innerText = 'Loading configuration...';

      const dlBtn = document.getElementById('btn-download-conf');
      if (dlBtn) {
        dlBtn.href = '/api/peers/' + encodeURIComponent(name) + '/download';
        dlBtn.setAttribute('download', name + '.conf');
        dlBtn.onclick = (e) => {
          if (currentConfigText) {
            e.preventDefault();
            downloadConfigFile(name, currentConfigText);
          }
        };
      }
      document.getElementById('qr-modal').style.display = 'flex';

      try {
        const cRes = await fetch('/api/peers/' + encodeURIComponent(name) + '/config');
        if (cRes.ok) {
          let text = await cRes.text();
          // Guarantee pure WireGuard .conf format (unwrap any JSON if ever present)
          try {
            const parsed = JSON.parse(text);
            if (parsed && typeof parsed === 'object') {
              if (parsed.config) text = parsed.config;
              else if (parsed.content) text = parsed.content;
            }
          } catch(e) {}

          currentConfigText = text.trim();
          preview.innerText = currentConfigText;

          if (window.renderSVGQRCode) {
            const svg = window.renderSVGQRCode(currentConfigText);
            if (svg) {
              box.innerHTML = svg;
              return;
            }
          }
          box.innerHTML = '<div style="color:#64748b; font-size:0.85rem;">QR Code available via Download</div>';
        } else {
          preview.innerText = 'Failed to load client configuration.';
          box.innerHTML = '<div class="text-danger small">Failed to load configuration.</div>';
        }
      } catch (e) {
        preview.innerText = 'Error fetching configuration.';
        box.innerHTML = '<div class="text-danger small">Network error fetching configuration.</div>';
      }
    }

    function copyConfigText() {
      if (!currentConfigText) return;
      navigator.clipboard.writeText(currentConfigText).then(() => {
        showToast('Configuration copied to clipboard!');
      }).catch(() => {
        showToast('Failed to copy configuration', true);
      });
    }

    function openChangePwModal() {
      document.getElementById('pw-old').value = '';
      document.getElementById('pw-new').value = '';
      document.getElementById('pw-modal').style.display = 'flex';
    }

    async function handleChangePw(e) {
      e.preventDefault();
      const old_pw = document.getElementById('pw-old').value;
      const new_pw = document.getElementById('pw-new').value;
      const res = await fetch('/api/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_password: old_pw, new_password: new_pw })
      });
      const data = await res.json();
      if (res.ok) {
        closeModal('pw-modal');
        showToast('Password updated successfully');
      } else {
        showToast(data.error || 'Failed to update password', true);
      }
    }

    // Auto-refresh data every 60 seconds (1 minute)
    setInterval(() => {
      if (document.getElementById('dashboard-view').style.display !== 'none') {
        loadData();
      }
    }, 60000);

    checkAuth();
