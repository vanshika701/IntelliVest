import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { modelsApi, resetModelCatalog, type ModelCatalog } from '../../api/models'
import { ModelSelect } from './ModelSelect'

const option = (key: string, label: string, isDefault = false, available = true) => ({
  key,
  label,
  description: `${label} description`,
  version: null,
  available,
  default: isDefault,
})

const catalog: ModelCatalog = {
  prediction: [option('lstm_lgbm', 'LSTM + LightGBM', true), option('lgbm', 'LightGBM')],
  sentiment: [option('distil', 'DistilRoBERTa', true)],
  summarizer: [option('extractive', 'Extractive', true), option('t5', 'T5-small'), option('gone', 'Gone', false, false)],
}

afterEach(() => {
  vi.restoreAllMocks()
  resetModelCatalog()
})

describe('ModelSelect', () => {
  it('marks the default, sends null for it and the key for another model', async () => {
    vi.spyOn(modelsApi, 'list').mockResolvedValue(catalog)
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ModelSelect kind="prediction" label="Prediction model" value={null} onChange={onChange} />)

    const select = await screen.findByLabelText('Prediction model')
    expect(select).toHaveValue('lstm_lgbm')
    expect(screen.getByRole('option', { name: /LSTM \+ LightGBM \(default/ })).toBeInTheDocument()

    await user.selectOptions(select, 'lgbm')
    expect(onChange).toHaveBeenLastCalledWith('lgbm')
    await user.selectOptions(select, 'lstm_lgbm')
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('hides models that are not available, and the picker when one model is left', async () => {
    vi.spyOn(modelsApi, 'list').mockResolvedValue(catalog)
    const { container } = render(<ModelSelect kind="sentiment" label="Sentiment model" value={null} onChange={() => {}} />)
    render(<ModelSelect kind="summarizer" label="Summary model" value="gone" onChange={() => {}} />)

    const summary = await screen.findByLabelText('Summary model')
    expect(summary).toHaveValue('extractive') // a remembered model that is gone falls back to the default
    expect(screen.queryByRole('option', { name: 'Gone' })).not.toBeInTheDocument()
    expect(container).toBeEmptyDOMElement()
  })
})
