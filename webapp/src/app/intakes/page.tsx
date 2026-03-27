'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '../../lib/graphql'
import DataTable, { Column } from '../../components/DataTable'

// For the global intakes list, you'd ideally have a direct query in the backend.
// Since we only query via Day/WeekPlan currently, we fetch recent week plans' days' intakes
// or just omit the global list and make it a pure child view. 
// Adding a stub component here for completeness of navigation.
export default function IntakesPage() {
  return (
    <div className="p-12 text-center text-slate-400">
      <h1 className="text-2xl font-bold mb-4 text-white">Intakes</h1>
      <p>Please browse to a specific Plan &gt; Day to view and manage intakes.</p>
    </div>
  )
}
