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
