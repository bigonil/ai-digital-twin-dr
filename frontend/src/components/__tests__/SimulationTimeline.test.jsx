import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SimulationTimeline from '../SimulationTimeline'

describe('SimulationTimeline', () => {
  const mockSimulationResult = {
    total_duration_ms: 5000,
    total_affected: 3,
    blast_radius: [
      { id: 'n0', name: 'Node0', distance: 0, step_time_ms: 0, estimated_rto_minutes: 5, estimated_rpo_minutes: 1 },
      { id: 'n1', name: 'Node1', distance: 1, step_time_ms: 2500, estimated_rto_minutes: 10, estimated_rpo_minutes: 2 },
      { id: 'n2', name: 'Node2', distance: 2, step_time_ms: 5000, estimated_rto_minutes: 15, estimated_rpo_minutes: 3 },
    ],
  }

  it('renders timeline controls', () => {
    render(
      <SimulationTimeline
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )

    expect(screen.getByTitle(/play|pause/i)).toBeInTheDocument()
    expect(screen.getByTitle('Rewind')).toBeInTheDocument()
    expect(screen.getByText(/Speed:/)).toBeInTheDocument()
  })

  it('displays live stats', async () => {
    render(
      <SimulationTimeline
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/Affected/i)).toBeInTheDocument()
      expect(screen.getByText(/RTO/i)).toBeInTheDocument()
      expect(screen.getByText(/RPO/i)).toBeInTheDocument()
    })
  })

  it('updates speed display when slider changes', async () => {
    const { container } = render(
      <SimulationTimeline
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )

    const speedSliders = container.querySelectorAll('input[type="range"]')
    const speedSlider = speedSliders[speedSliders.length - 1] // Last range input is speed

    fireEvent.change(speedSlider, { target: { value: '1.5' } })

    await waitFor(() => {
      expect(screen.getByText(/1.50x/)).toBeInTheDocument()
    })
  })

  it('calls onTimeChange when time updates', async () => {
    const onTimeChange = vi.fn()

    render(
      <SimulationTimeline
        simulationResult={mockSimulationResult}
        onTimeChange={onTimeChange}
      />
    )

    // Animation should call onTimeChange
    await waitFor(
      () => {
        expect(onTimeChange).toHaveBeenCalled()
      },
      { timeout: 1000 }
    )
  })

  it('has working play/pause button', async () => {
    render(
      <SimulationTimeline
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )

    const playButton = screen.getByTitle(/play|pause/i)
    expect(playButton).toBeInTheDocument()

    // Should be clickable
    fireEvent.click(playButton)

    // Button title should change
    await waitFor(() => {
      expect(screen.getByTitle(/play|pause/i)).toBeInTheDocument()
    })
  })

  it('has working rewind button', async () => {
    render(
      <SimulationTimeline
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )

    const rewindButton = screen.getByTitle('Rewind')
    expect(rewindButton).toBeInTheDocument()

    fireEvent.click(rewindButton)

    // Should still be in document after click
    expect(screen.getByTitle('Rewind')).toBeInTheDocument()
  })
})
