# Home Assistant (GitOps-managed)

- Single replica (Home Assistant is not cluster-aware; avoids config corruption)
- Config PVC: homeassistant-config (Longhorn, RWX)

## Configuration Management

### ConfigMaps

Home Assistant configuration is managed through Kubernetes ConfigMaps for different components:

- **Automations**: `homeassistant-automations` - File-based automations from `configuration/automations/` directory
- **Blueprints**: `homeassistant-blueprints` - Automation blueprints from `configuration/blueprints/automation/` directory  
- **Scripts**: `homeassistant-scripts` - File-based scripts from `configuration/scripts/` directory
- **Helpers**: Domain-organized input helpers:
  - `homeassistant-helpers-input-boolean` - Boolean switches and toggles
  - `homeassistant-helpers-input-datetime` - Time pickers for schedule windows
  - `homeassistant-helpers-input-select` - Scene selection dropdowns
  - `homeassistant-helpers-input-number` - Brightness and numeric controls
  - `homeassistant-helpers-input-text` - Text input helpers
- **Dashboards**: `homeassistant-dashboards` - Lovelace dashboard views

### Generation Scripts

All ConfigMaps are generated from source files using a unified generation script:

```bash
# Generate all ConfigMaps (automations, blueprints, dashboards, scripts, helpers)
cd configuration/
./generate-configmaps.sh
```

The unified script will:
1. Generate ConfigMaps for automations, blueprints, dashboards, and scripts from their respective directories
2. For helpers: first run Jinja2 template generation (requires `jinja2-cli`), then create ConfigMaps from the generated files

All generated ConfigMap YAML files are written to the parent directory (top level of `home-assistant/`).

### Directory Structure

```
gitops/apps/home-assistant/
├── configuration/
│   ├── generate-configmaps.sh (unified generation script)
│   ├── automations/
│   │   └── *.yaml (automation files)
│   ├── blueprints/
│   │   └── automation/*.yaml (blueprint files)
│   ├── dashboards/
│   │   └── *.yaml (dashboard view files)
│   ├── scripts/
│   │   └── *.yaml (script files)
│   └── helpers/
│       ├── generate_helpers.sh (Jinja2 template generator)
│       ├── *_template.yaml.j2 (Jinja2 templates)
│       ├── input_text/ (static text helper files)
│       └── generated/ (domain-organized helper files)
│           ├── input_boolean/
│           ├── input_datetime/
│           ├── input_select/
│           ├── input_number/
│           └── input_text/
├── *-configmap.yaml (generated ConfigMaps - K3s resources)
├── deployment.yaml (K3s resource)
├── ingress.yaml (K3s resource)
├── namespace.yaml (K3s resource)
├── service.yaml (K3s resource)
└── storage.yaml (K3s resource)
```

### Configuration Features

- **Hybrid Dashboard Mode**: Supports both YAML-managed dashboards and UI-created ones
- **Domain-Organized Helpers**: Input helpers split by type for cleaner configuration management
- **Preserved UI Editing**: UI-created automations, scripts, and scenes are preserved during deployments
- **GitOps Integration**: All configuration managed through Git and automatically deployed