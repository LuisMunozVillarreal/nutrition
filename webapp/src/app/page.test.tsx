import React from 'react';
import { render, screen } from '@testing-library/react';

import Home from './page';

describe('page tests', () => {
  it('renders Home', () => {
    expect.assertions(1);

    // When
    render(<Home />);

    // Then
    expect(screen.getByText(/Get started/i)).toBeInTheDocument();
  });
});
