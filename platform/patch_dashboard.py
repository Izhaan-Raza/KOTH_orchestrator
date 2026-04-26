import bs4

with open('templates/dashboard.html', 'r') as f:
    soup = bs4.BeautifulSoup(f.read(), 'html.parser')

# 1. Modify Tabs
tabs = soup.find(class_='tabs')
if tabs:
    routing_tab = tabs.find('button', {'data-tab-target': 'routingTab'})
    if routing_tab:
        routing_tab.string = 'Nodes'
        
    health_tab = tabs.find('button', {'data-tab-target': 'healthTab'})
    if health_tab:
        health_tab.string = 'Registry'

# 2. Add Account Creation to Operations Tab
ops_tab = soup.find(id='operationsTab')
if ops_tab:
    accounts_html = """
    <article class="panel">
      <header class="panel-head">
        <h2>Account Management</h2>
        <p>Create players and platform admins.</p>
      </header>
      <div class="inline-form">
        <label>Username</label>
        <input id="newAccountUsername" type="text" placeholder="Username" />
        <label>Password</label>
        <input id="newAccountPassword" type="password" placeholder="Password" />
        <select id="newAccountRole">
          <option value="player">Player</option>
          <option value="admin">Admin</option>
        </select>
        <button id="createAccountBtn" type="button">Create</button>
      </div>
      <div class="table-wrap tall">
        <table>
          <thead><tr><th>ID</th><th>Username</th><th>Role</th><th>Created</th><th>Action</th></tr></thead>
          <tbody id="accountsTable"></tbody>
        </table>
      </div>
    </article>
    """
    ops_tab.append(bs4.BeautifulSoup(accounts_html, 'html.parser'))

# 3. Add Node IP Mappings to Routing (Nodes) Tab
routing_tab_panel = soup.find(id='routingTab')
if routing_tab_panel:
    nodes_html = """
    <article class="panel">
      <header class="panel-head">
        <h2>Infrastructure Nodes</h2>
        <p>Map physical IPs for machine deployments.</p>
      </header>
      <div class="inline-form">
        <label>Name</label>
        <input id="newNodeName" type="text" placeholder="e.g. Node 1" />
        <label>Host IP</label>
        <input id="newNodeIp" type="text" placeholder="192.168.1.10" />
        <button id="createNodeBtn" type="button">Register</button>
      </div>
      <div class="table-wrap medium">
        <table>
          <thead><tr><th>Name</th><th>Host IP</th><th>Status</th><th>SSH User</th><th>Action</th></tr></thead>
          <tbody id="nodesTable"></tbody>
        </table>
      </div>
    </article>
    """
    routing_tab_panel.insert(0, bs4.BeautifulSoup(nodes_html, 'html.parser'))

# 4. Add Upload to Health (Registry) Tab
health_tab_panel = soup.find(id='healthTab')
if health_tab_panel:
    upload_html = """
    <article class="panel">
      <header class="panel-head">
        <h2>Machine Registry</h2>
        <p>Upload new machines (.zip containing koth-machine.yaml) and view registered machines.</p>
      </header>
      <div class="inline-form">
        <label>Machine Archive</label>
        <input id="newMachineFile" type="file" accept=".zip" />
        <button id="uploadMachineBtn" type="button">Upload</button>
      </div>
      <div class="table-wrap medium">
        <table>
          <thead><tr><th>Name</th><th>Difficulty</th><th>Points</th><th>Status</th><th>Action</th></tr></thead>
          <tbody id="machinesRegistryTable"></tbody>
        </table>
      </div>
    </article>
    """
    health_tab_panel.insert(0, bs4.BeautifulSoup(upload_html, 'html.parser'))

# 5. Inject new JS script
new_js = """
<script>
  async function loadV2Data() {
    // Accounts
    try {
      const accounts = await getJson('/api/accounts');
      document.getElementById('accountsTable').innerHTML = accounts.map(a => `
        <tr><td>${a.id.slice(0,8)}</td><td>${escapeHtml(a.username)}</td><td>${a.role}</td><td>${new Date(a.created_at).toLocaleString()}</td>
        <td><button onclick="del('/api/accounts/${a.id}')">Delete</button></td></tr>
      `).join('');
    } catch(e) {}

    // Nodes
    try {
      const nodes = await getJson('/api/nodes');
      document.getElementById('nodesTable').innerHTML = nodes.map(n => `
        <tr><td>${escapeHtml(n.name)}</td><td>${escapeHtml(n.host_ip)}</td><td><span class="pill tone-ok">${n.status}</span></td><td>${n.ssh_user}</td>
        <td><button onclick="del('/api/nodes/${n.id}')">Delete</button></td></tr>
      `).join('');
    } catch(e) {}

    // Machines
    try {
      const machines = await getJson('/api/machines');
      document.getElementById('machinesRegistryTable').innerHTML = machines.map(m => `
        <tr><td>${escapeHtml(m.name)}</td><td><span class="pill">${m.difficulty}</span></td><td>${m.points_per_tick}</td><td><span class="pill ${m.status === 'registered' ? 'tone-ok' : 'tone-warning'}">${m.status}</span></td>
        <td><button onclick="post('/api/deploy', {machine_id: '${m.id}', node_host: '127.0.0.1', node_ssh_user: 'ubuntu'})">Deploy</button></td></tr>
      `).join('');
    } catch(e) {}
  }

  document.addEventListener('DOMContentLoaded', () => {
    setInterval(() => {
      if (dashboardConnected) loadV2Data();
    }, 5000);
    
    document.getElementById('createAccountBtn')?.addEventListener('click', async () => {
      await post('/api/accounts', {
        username: document.getElementById('newAccountUsername').value,
        password: document.getElementById('newAccountPassword').value,
        role: document.getElementById('newAccountRole').value
      });
      document.getElementById('newAccountUsername').value = '';
      document.getElementById('newAccountPassword').value = '';
      loadV2Data();
    });

    document.getElementById('createNodeBtn')?.addEventListener('click', async () => {
      await post('/api/nodes', {
        name: document.getElementById('newNodeName').value,
        host_ip: document.getElementById('newNodeIp').value,
        ssh_user: "ubuntu"
      });
      document.getElementById('newNodeName').value = '';
      document.getElementById('newNodeIp').value = '';
      loadV2Data();
    });

    document.getElementById('uploadMachineBtn')?.addEventListener('click', async () => {
      const fileInput = document.getElementById('newMachineFile');
      if (!fileInput.files.length) return alert('Select a zip file');
      const formData = new FormData();
      formData.append('archive', fileInput.files[0]);
      
      const res = await fetch('/api/machines/upload', {
        method: 'POST',
        headers: { 'X-API-Key': document.getElementById('apiKey').value },
        body: formData
      });
      if (!res.ok) alert('Upload failed');
      else { alert('Uploaded!'); loadV2Data(); }
    });
  });
</script>
"""
soup.append(bs4.BeautifulSoup(new_js, 'html.parser'))

with open('templates/dashboard.html', 'w') as f:
    f.write(str(soup))
