{{/*
Expand the name of the chart.
*/}}
{{- define "meraki-dashboard-exporter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "meraki-dashboard-exporter.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "meraki-dashboard-exporter.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "meraki-dashboard-exporter.labels" -}}
helm.sh/chart: {{ include "meraki-dashboard-exporter.chart" . }}
{{ include "meraki-dashboard-exporter.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "meraki-dashboard-exporter.selectorLabels" -}}
app.kubernetes.io/name: {{ include "meraki-dashboard-exporter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use.
*/}}
{{- define "meraki-dashboard-exporter.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "meraki-dashboard-exporter.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the name of the Secret containing the Meraki API key.
If meraki.existingSecret is set that name is used, otherwise the generated Secret name.
*/}}
{{- define "meraki-dashboard-exporter.secretName" -}}
{{- if .Values.meraki.existingSecret }}
{{- .Values.meraki.existingSecret }}
{{- else }}
{{- include "meraki-dashboard-exporter.fullname" . }}
{{- end }}
{{- end }}

{{/*
Return the key within the Secret that holds the API key value.
*/}}
{{- define "meraki-dashboard-exporter.secretKey" -}}
{{- if .Values.meraki.existingSecret }}
{{- .Values.meraki.existingSecretKey }}
{{- else }}
{{- "api-key" }}
{{- end }}
{{- end }}
