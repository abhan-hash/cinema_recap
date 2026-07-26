import { useEffect, useState } from 'react'

const STEPS = [
  { id: 1, label: 'Loading Archive Data...' },
  { id: 2, label: 'AI Director Analyzing...' },
  { id: 3, label: 'Optimizing Video Stream...' },
  { id: 4, label: 'Ready...' },
]

export default function GeneratingScreen({ step }) {
  const currentStep = STEPS.find(s => s.id === step) || STEPS[0]

  return (
    <div className="generating-screen">
      <div className="netflix-spinner" />
      <div className="generating-step-text">
        {currentStep.label}
      </div>
    </div>
  )
}
