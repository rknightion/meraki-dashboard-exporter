{{/*
Validate that exactly one of meraki.apiKey or meraki.existingSecret is provided.
This template is called from each resource template to ensure validation runs.
*/}}
{{- define "meraki-dashboard-exporter.validateApiKey" -}}
{{- if and .Values.meraki.apiKey .Values.meraki.existingSecret }}
{{- fail "Only one of meraki.apiKey or meraki.existingSecret may be set, not both." }}
{{- end }}

{{- if not (or .Values.meraki.apiKey .Values.meraki.existingSecret) }}
{{- fail "One of meraki.apiKey or meraki.existingSecret must be set." }}
{{- end }}
{{- end }}

{{/*
The pod must outlive one logical API fetch plus a fixed shutdown-drain margin.
The config value is chart-managed so this relationship is render-time verifiable.
*/}}
{{- define "meraki-dashboard-exporter.validateShutdownGrace" -}}
{{- $deadline := int (default 120 .Values.config.apiPerFetchDeadlineSeconds) -}}
{{- $minimumGrace := add $deadline 30 -}}
{{- if lt (int .Values.terminationGracePeriodSeconds) $minimumGrace }}
{{- fail (printf "terminationGracePeriodSeconds must be at least config.apiPerFetchDeadlineSeconds + 30 (%d); got %d" $minimumGrace (int .Values.terminationGracePeriodSeconds)) }}
{{- end }}
{{- range .Values.extraEnv }}
{{- if eq .name "MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS" }}
{{- fail "extraEnv may not set MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS; use config.apiPerFetchDeadlineSeconds so termination grace is validated." }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Validate that config.otelEndpoint is set whenever config.otelEnabled is truthy.
Mirrors OTelSettings.validate_endpoint in core/config_models.py, which raises at
application startup on the same condition -- failing here instead means a
misconfiguration is caught at `helm install`/`helm template` time rather than
surfacing as a CrashLoopBackOff.
*/}}
{{- define "meraki-dashboard-exporter.validateOtel" -}}
{{- if and (eq (.Values.config.otelEnabled | toString) "true") (not .Values.config.otelEndpoint) }}
{{- fail "config.otelEndpoint must be set when config.otelEnabled is true." }}
{{- end }}
{{- end }}
