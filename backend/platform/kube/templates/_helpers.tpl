{{/*
Expand the name of the chart.
*/}}
{{- define "nutrition.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "nutrition.fullname" -}}
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
{{- define "nutrition.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "nutrition.labels" -}}
helm.sh/chart: {{ include "nutrition.chart" . }}
{{ include "nutrition.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote | replace "+" "_" }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "nutrition.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nutrition.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "nutrition.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "nutrition.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Validate one active Garmin URL or comma-separated origin list.
*/}}
{{- define "nutrition.validateGarminRuntimeUrl" -}}
{{- $name := .name -}}
{{- $origin := .origin -}}
{{- range $candidate := splitList "," (toString .value) -}}
{{- $value := trim $candidate -}}
{{- if or (empty $value) (contains "${" $value) (contains "<" $value) (contains ">" $value) (regexMatch "[[:space:]]" $value) -}}
{{- fail (printf "active Garmin scheduler requires %s to contain complete non-placeholder HTTPS values" $name) -}}
{{- end -}}
{{- $parsed := urlParse $value -}}
{{- $scheme := lower (get $parsed "scheme") -}}
{{- $host := lower (get $parsed "host") -}}
{{- $userinfo := get $parsed "userinfo" -}}
{{- if or (ne $scheme "https") (empty $host) (not (empty $userinfo)) -}}
{{- fail (printf "active Garmin scheduler requires %s to contain complete non-placeholder HTTPS values" $name) -}}
{{- end -}}
{{- if or (regexMatch "(^|\\.)example\\.(com|net|org)(:[0-9]+)?$" $host) (regexMatch "(^|\\.)(invalid|localhost|test|local)(:[0-9]+)?$" $host) -}}
{{- fail (printf "active Garmin scheduler requires %s to contain complete non-placeholder HTTPS values" $name) -}}
{{- end -}}
{{- if not (empty (get $parsed "fragment")) -}}
{{- fail (printf "active Garmin scheduler requires %s to contain complete non-placeholder HTTPS values" $name) -}}
{{- end -}}
{{- if and $origin (or (not (has (get $parsed "path") (list "" "/"))) (not (empty (get $parsed "query")))) -}}
{{- fail (printf "active Garmin scheduler requires %s origins to be pathless" $name) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Fail rendering when an enabled, unsuspended Garmin scheduler is incomplete.
*/}}
{{- define "nutrition.validateGarminSchedulerActivation" -}}
{{- $sync := .Values.garminSync | default dict -}}
{{- $enabled := false -}}
{{- if hasKey $sync "enabled" -}}
{{- if not (kindIs "bool" $sync.enabled) -}}
{{- fail "garminSync.enabled must be a boolean" -}}
{{- end -}}
{{- $enabled = $sync.enabled -}}
{{- end -}}
{{- $suspended := true -}}
{{- if hasKey $sync "suspend" -}}
{{- if not (kindIs "bool" $sync.suspend) -}}
{{- fail "garminSync.suspend must be a boolean" -}}
{{- end -}}
{{- $suspended = $sync.suspend -}}
{{- end -}}
{{- if and $enabled (not $suspended) -}}
{{- $environment := .Values.env | default list -}}
{{- $enabledFound := false -}}
{{- $enabledValue := "" -}}
{{- range $entry := $environment -}}
{{- if eq (get $entry "name") "GARMIN_ENABLED" -}}
{{- $enabledFound = true -}}
{{- if hasKey $entry "value" -}}
{{- $enabledValue = lower (trim (toString (get $entry "value"))) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if or (not $enabledFound) (ne $enabledValue "true") -}}
{{- fail "active Garmin scheduler requires backend and CronJob GARMIN_ENABLED=true" -}}
{{- end -}}
{{- $requiredUrls := list "GARMIN_AUTHORIZATION_URL" "GARMIN_TOKEN_URL" "GARMIN_ACTIVITIES_URL" "GARMIN_REVOKE_TOKEN_URL" "GARMIN_CALLBACK_URL" "GARMIN_PROVIDER_ORIGINS" "GARMIN_CALLBACK_ALLOWED_ORIGINS" -}}
{{- range $name := $requiredUrls -}}
{{- $found := false -}}
{{- $value := "" -}}
{{- range $entry := $environment -}}
{{- if eq (get $entry "name") $name -}}
{{- $found = true -}}
{{- if hasKey $entry "value" -}}
{{- $value = toString (get $entry "value") -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if not $found -}}
{{- fail (printf "active Garmin scheduler requires %s" $name) -}}
{{- end -}}
{{- include "nutrition.validateGarminRuntimeUrl" (dict "name" $name "value" $value "origin" (hasSuffix "ORIGINS" $name)) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Image tag without +
*/}}
{{- define "nutrition.imageTag" -}}
{{ .Chart.AppVersion | replace "+" "_" }}
{{- end }}
