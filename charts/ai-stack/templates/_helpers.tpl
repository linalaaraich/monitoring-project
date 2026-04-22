{{/*
Expand the name of the chart.
*/}}
{{- define "ai-stack.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ai-stack.fullname" -}}
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
{{- define "ai-stack.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ai-stack.labels" -}}
helm.sh/chart: {{ include "ai-stack.chart" . }}
{{ include "ai-stack.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ai-stack.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ai-stack.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Compose upstream monitoring URLs. Prefer explicit per-URL values, else
compose from monitoring.host + port. Fails validation if neither is set —
better to error on install than silently produce http://:9090/ and fail
at runtime with DNS errors (see earlier "MONITORING_VM_IP" placeholder bug).
*/}}
{{- define "ai-stack.prometheusUrl" -}}
{{- if .Values.monitoring.prometheusUrl -}}
{{- .Values.monitoring.prometheusUrl -}}
{{- else if .Values.monitoring.host -}}
http://{{ .Values.monitoring.host }}:{{ .Values.monitoring.prometheusPort | default 9090 }}
{{- else -}}
{{- fail "ai-stack: set monitoring.host (preferred) or monitoring.prometheusUrl" -}}
{{- end -}}
{{- end }}

{{- define "ai-stack.lokiUrl" -}}
{{- if .Values.monitoring.lokiUrl -}}
{{- .Values.monitoring.lokiUrl -}}
{{- else if .Values.monitoring.host -}}
http://{{ .Values.monitoring.host }}:{{ .Values.monitoring.lokiPort | default 3100 }}
{{- else -}}
{{- fail "ai-stack: set monitoring.host (preferred) or monitoring.lokiUrl" -}}
{{- end -}}
{{- end }}

{{- define "ai-stack.jaegerUrl" -}}
{{- if .Values.monitoring.jaegerUrl -}}
{{- .Values.monitoring.jaegerUrl -}}
{{- else if .Values.monitoring.host -}}
http://{{ .Values.monitoring.host }}:{{ .Values.monitoring.jaegerPort | default 16686 }}
{{- else -}}
{{- fail "ai-stack: set monitoring.host (preferred) or monitoring.jaegerUrl" -}}
{{- end -}}
{{- end }}

{{- define "ai-stack.grafanaDashboardUrl" -}}
{{- if .Values.grafanaDashboardUrl -}}
{{- .Values.grafanaDashboardUrl -}}
{{- else if .Values.monitoring.host -}}
http://{{ .Values.monitoring.host }}:3000
{{- else -}}
http://
{{- end -}}
{{- end }}
