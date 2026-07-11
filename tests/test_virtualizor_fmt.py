"""Formattatori Virtualizor: strutture reali (server=lista, ips=dict) e conversioni GB."""

from mcp_servers import virtualizor_read as vz


def test_fmt_servers_ram_in_gb():
    data = {"servers": [{
        "serid": 0, "server_name": "CN1", "ip": "10.0.0.1", "virt": "kvm",
        "ram": "209629", "total_ram": "225121", "space": "3940",
        "total_space": "4242", "os": "AlmaLinux 9.8",
    }]}
    out = vz._fmt_servers(data)
    assert "CN1" in out
    assert "GB" in out and "MB" not in out           # RAM ora in GB, non MB
    assert "220" in out                              # 225121 MB ~ 220 GB


def test_fmt_vps_list_ips_dict_and_suspended():
    data = {"vs": {"1": {
        "vps_name": "v1", "hostname": "h1.it", "ips": {"1": "1.2.3.4"},
        "virt": "kvm", "ram": "8192", "cores": "4", "suspended": "1",
    }}}
    out = vz._fmt_vps_list(data)
    assert "1.2.3.4" in out                          # ips è un dict, va estratto
    assert "SOSPESA" in out


def test_fmt_vps_stats_status_and_cpu():
    data = {"vps_data": {"1": {
        "status": "1", "used_cpu": "12", "used_ram": "800", "ram": "2048",
        "used_disk": "10", "disk": "40", "used_bandwidth": "5", "bandwidth": "0",
        "vps_name": "v1", "hostname": "h1.it",
    }}}
    out = vz._fmt_vps_stats(data)
    assert "online" in out
    assert "12" in out                               # CPU %
    assert "illimitata" in out                       # bandwidth 0 = illimitata
