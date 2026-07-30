export function waitForFormReady() {
    cy.get('[data-testid="form-ready"]', { timeout: 10000 }).should('be.visible');
}

export function replaceInputValue(
    selector: string,
    value: string,
    options: { force?: boolean } = {},
) {
    cy.get<HTMLInputElement>(selector).clear(options);
    cy.get<HTMLInputElement>(selector).should('have.value', '');
    cy.get<HTMLInputElement>(selector).type(value, options);
    cy.get<HTMLInputElement>(selector).should('have.value', value);
}
