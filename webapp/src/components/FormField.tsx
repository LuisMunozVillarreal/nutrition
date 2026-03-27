'use client'

interface FormFieldProps {
  label: string
  name: string
  value: string | number
  onChange: (name: string, value: string) => void
  type?: 'text' | 'number' | 'date' | 'time' | 'email' | 'url'
  required?: boolean
  readOnly?: boolean
  placeholder?: string
  step?: string
  min?: string | number
  max?: string | number
  helpText?: string
  testId?: string
}

export function FormField({
  label,
  name,
  value,
  onChange,
  type = 'text',
  required = false,
  readOnly = false,
  placeholder,
  step,
  min,
  max,
  helpText,
  testId,
}: FormFieldProps) {
  return (
    <div className="form-group">
      <label className="form-label" htmlFor={name}>
        {label}
        {required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        value={value ?? ''}
        onChange={(e) => onChange(name, e.target.value)}
        className="form-input"
        required={required}
        readOnly={readOnly}
        disabled={readOnly}
        placeholder={placeholder}
        step={step}
        min={min}
        max={max}
        data-testid={testId || `field-${name}`}
      />
      {helpText && (
        <p className="text-xs text-slate-500 mt-1">{helpText}</p>
      )}
    </div>
  )
}

interface SelectFieldProps {
  label: string
  name: string
  value: string
  onChange: (name: string, value: string) => void
  options: { value: string; label: string }[]
  required?: boolean
  readOnly?: boolean
  testId?: string
  helpText?: string
}

export function SelectField({
  label,
  name,
  value,
  onChange,
  options,
  required = false,
  readOnly = false,
  testId,
  helpText,
}: SelectFieldProps) {
  return (
    <div className="form-group">
      <label className="form-label" htmlFor={name}>
        {label}
        {required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      <select
        id={name}
        name={name}
        value={value ?? ''}
        onChange={(e) => onChange(name, e.target.value)}
        className="form-input"
        required={required}
        disabled={readOnly}
        data-testid={testId || `field-${name}`}
      >
        <option value="">— Select —</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {helpText && (
        <p className="text-xs text-slate-500 mt-1">{helpText}</p>
      )}
    </div>
  )
}

interface TextareaFieldProps {
  label: string
  name: string
  value: string
  onChange: (name: string, value: string) => void
  required?: boolean
  readOnly?: boolean
  rows?: number
  placeholder?: string
  testId?: string
}

export function TextareaField({
  label,
  name,
  value,
  onChange,
  required = false,
  readOnly = false,
  rows = 3,
  placeholder,
  testId,
}: TextareaFieldProps) {
  return (
    <div className="form-group">
      <label className="form-label" htmlFor={name}>
        {label}
        {required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      <textarea
        id={name}
        name={name}
        value={value ?? ''}
        onChange={(e) => onChange(name, e.target.value)}
        className="form-input"
        required={required}
        readOnly={readOnly}
        disabled={readOnly}
        rows={rows}
        placeholder={placeholder}
        data-testid={testId || `field-${name}`}
      />
    </div>
  )
}

interface CheckboxFieldProps {
  label: string
  name: string
  checked: boolean
  onChange: (name: string, checked: boolean) => void
  readOnly?: boolean
  testId?: string
  helpText?: string
}

export function CheckboxField({
  label,
  name,
  checked,
  onChange,
  readOnly = false,
  testId,
  helpText,
}: CheckboxFieldProps) {
  return (
    <div className="form-group mb-0">
      <div className="flex items-center gap-2">
        <input
          id={name}
          name={name}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(name, e.target.checked)}
          disabled={readOnly}
          className="w-4 h-4 accent-purple-500"
          data-testid={testId || `field-${name}`}
        />
        <label className="form-label cursor-pointer mb-0" htmlFor={name}>
          {label}
        </label>
      </div>
      {helpText && (
        <p className="text-xs text-slate-500 mt-1">{helpText}</p>
      )}
    </div>
  )
}

interface ReadonlyFieldProps {
  label: string
  value: React.ReactNode
  testId?: string
}

export function ReadonlyField({ label, value, testId }: ReadonlyFieldProps) {
  return (
    <div className="form-group">
      <span className="form-label">{label}</span>
      <div
        className="form-input bg-transparent border-transparent px-0 text-slate-300"
        data-testid={testId}
      >
        {value ?? '—'}
      </div>
    </div>
  )
}
