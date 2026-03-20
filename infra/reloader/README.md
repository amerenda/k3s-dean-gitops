# Reloader

This directory contains the configuration for the Stakater Reloader Helm chart.

## Overview

Reloader can watch changes in ConfigMap and Secret and do rolling upgrades on Pods with their associated DeploymentConfigs, Deployments, Daemonsets and Statefulsets.

## Configuration

- **Chart**: stakater/reloader
- **Version**: 2.2.3
- **Repository**: https://stakater.github.io/stakater-charts

## Features

- Automatically restarts pods when ConfigMaps or Secrets change
- Supports multiple resource types (Deployments, StatefulSets, DaemonSets)
- Configurable watch scope (namespace or cluster-wide)
- Lightweight and efficient

## Usage

The reloader will automatically watch for changes in ConfigMaps and Secrets that are annotated with:

```yaml
metadata:
  annotations:
    reloader.stakater.com/auto: "true"
```

Or for specific resources:

```yaml
metadata:
  annotations:
    reloader.stakater.com/match: "true"
```

## Resources

- [GitHub Repository](https://github.com/stakater/Reloader)
- [Helm Chart Documentation](https://github.com/stakater/Reloader/tree/master/deployments/kubernetes/chart/reloader)
