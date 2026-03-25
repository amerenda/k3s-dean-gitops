# Mac Mini DNS Migration — Options

Colima (Docker on macOS via VM) cannot bind containers to the host's
LAN IP on port 53 due to: macOS mDNSResponder owns port 53 (SIP protected),
and Lima's SSH tunnel only binds to 127.0.0.1.

## Options

### Option 1: OrbStack (recommended)
- macOS-native Docker runtime, no VM
- Containers bind directly to host network interfaces
- `docker run -p 10.100.20.18:53:53 pihole` just works
- $8/month personal license or free for personal/hobby
- Install: `brew install orbstack`
- Zero config changes to docker-compose.yaml needed

### Option 2: Docker Desktop for Mac
- Official Docker for Mac, uses lightweight VM
- Supports binding to host IPs natively
- Free for personal use
- Install: `brew install --cask docker`

### Option 3: Run DNS natively (no Docker)
- Install Pi-hole and BIND9 via Homebrew/macports directly on macOS
- No VM overhead, direct port binding
- More manual maintenance (no container image updates)
- BIND9: `brew install bind`
- Pi-hole: Manual install (not officially supported on macOS)

### Option 4: Keep DNS on k3s
- Don't migrate DNS to Mac Mini
- Only migrate Home Assistant and Whisper
- Pi-hole and BIND9 stay on k3s (rpi5-0)
- Simplest, least disruptive

### Current recommendation
Option 1 (OrbStack) for full migration, or Option 4 to defer DNS migration
and just move HA to the Mac Mini for now.
